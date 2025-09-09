# app/core/monitoring.py - Rate Limiting Monitoring & Alerting

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from dataclasses import dataclass
from .content_rate_limiter import content_rate_limiter
from .rate_limit_decorator import read_rate_limiter
import structlog

logger = structlog.get_logger("monitoring")

@dataclass
class Alert:
    alert_type: str
    severity: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    resolved: bool = False

class RateLimitMonitor:

    def __init__(self):
        self.alerts: List[Alert] = []
        self.alert_thresholds = {
            "burst_lockouts": 10,
            "daily_limit_hits": 5,
            "suspicious_patterns": 3,
            "read_abuse": 50
        }

    def check_rate_limit_health(self) -> Dict[str, Any]:

        now = time.time()
        hour_ago = now - 3600

        content_stats = self._analyze_content_rate_limits(hour_ago)

        read_stats = self._analyze_read_rate_limits(hour_ago)

        alerts = self._check_for_alerts(content_stats, read_stats)

        health_score = self._calculate_health_score(content_stats, read_stats)

        return {
            "health_score": health_score,
            "status": self._get_status_from_score(health_score),
            "content_rate_limits": content_stats,
            "read_rate_limits": read_stats,
            "alerts": [alert.__dict__ for alert in alerts],
            "recommendations": self._generate_recommendations(content_stats, read_stats),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _analyze_content_rate_limits(self, hour_ago: float) -> Dict[str, Any]:

        stats = {
            "active_users": 0,
            "total_lockouts": len(content_rate_limiter.lockouts),
            "lockouts_by_type": {},
            "burst_lockouts_1h": 0,
            "daily_limit_hits_1h": 0,
            "top_limited_content_types": {},
            "user_tier_distribution": {"new": 0, "regular": 0, "established": 0, "trusted": 0}
        }

        current_time = time.time()
        for lockout_key, lockout_time in content_rate_limiter.lockouts.items():
            if current_time < lockout_time:
                user_id, content_type = lockout_key.split(":", 1)
                stats["lockouts_by_type"][content_type] = stats["lockouts_by_type"].get(content_type, 0) + 1

        for user_id, content_attempts in content_rate_limiter.attempts.items():
            user_has_recent_activity = False

            for content_type, attempts in content_attempts.items():
                recent_attempts = [
                    (timestamp, count) for timestamp, count in attempts
                    if timestamp > hour_ago
                ]

                if recent_attempts:
                    user_has_recent_activity = True
                    stats["top_limited_content_types"][content_type] = \
                        stats["top_limited_content_types"].get(content_type, 0) + len(recent_attempts)

            if user_has_recent_activity:
                stats["active_users"] += 1

        return stats

    def _analyze_read_rate_limits(self, hour_ago: float) -> Dict[str, Any]:

        stats = {
            "active_ips": 0,
            "blocked_reads_1h": 0,
            "top_limited_endpoints": {},
            "suspicious_ips": []
        }

        for ip, endpoint_attempts in read_rate_limiter.attempts.items():
            ip_has_recent_activity = False
            ip_total_attempts = 0

            for endpoint_type, attempts in endpoint_attempts.items():
                recent_attempts = [
                    (timestamp, count) for timestamp, count in attempts
                    if timestamp > hour_ago
                ]

                if recent_attempts:
                    ip_has_recent_activity = True
                    attempt_count = sum(count for _, count in recent_attempts)
                    ip_total_attempts += attempt_count

                    stats["top_limited_endpoints"][endpoint_type] = \
                        stats["top_limited_endpoints"].get(endpoint_type, 0) + attempt_count

            if ip_has_recent_activity:
                stats["active_ips"] += 1

                if ip_total_attempts > 500:
                    stats["suspicious_ips"].append({
                        "ip": ip,
                        "attempts_1h": ip_total_attempts,
                        "endpoints": list(endpoint_attempts.keys())
                    })

        return stats

    def _check_for_alerts(self, content_stats: Dict, read_stats: Dict) -> List[Alert]:

        alerts = []
        now = datetime.now(timezone.utc)

        if content_stats["total_lockouts"] > self.alert_thresholds["burst_lockouts"]:
            alerts.append(Alert(
                alert_type="high_lockout_rate",
                severity="high",
                message=f"High number of rate limit lockouts: {content_stats['total_lockouts']}",
                details={"lockouts_by_type": content_stats["lockouts_by_type"]},
                timestamp=now
            ))

        if len(read_stats["suspicious_ips"]) > self.alert_thresholds["suspicious_patterns"]:
            alerts.append(Alert(
                alert_type="suspicious_read_patterns",
                severity="medium",
                message=f"Detected {len(read_stats['suspicious_ips'])} IPs with suspicious read patterns",
                details={"suspicious_ips": read_stats["suspicious_ips"][:5]},  # Top 5
                timestamp=now
            ))

        if read_stats["active_ips"] > self.alert_thresholds["read_abuse"]:
            alerts.append(Alert(
                alert_type="read_abuse_spike",
                severity="medium",
                message=f"High number of IPs hitting read rate limits: {read_stats['active_ips']}",
                details={"top_endpoints": read_stats["top_limited_endpoints"]},
                timestamp=now
            ))

        self.alerts.extend(alerts)

        for alert in alerts:
            if alert.severity in ["high", "critical"]:
                logger.warning(
                    f"Rate limiting alert: {alert.message}",
                    alert_type=alert.alert_type,
                    severity=alert.severity,
                    details=alert.details
                )

        return alerts

    def _calculate_health_score(self, content_stats: Dict, read_stats: Dict) -> int:

        score = 100

        if content_stats["total_lockouts"] > 20:
            score -= 30
        elif content_stats["total_lockouts"] > 10:
            score -= 15
        elif content_stats["total_lockouts"] > 5:
            score -= 5

        suspicious_count = len(read_stats["suspicious_ips"])
        if suspicious_count > 10:
            score -= 25
        elif suspicious_count > 5:
            score -= 15
        elif suspicious_count > 2:
            score -= 5

        if read_stats["active_ips"] > 100:
            score -= 20
        elif read_stats["active_ips"] > 50:
            score -= 10

        return max(0, score)

    def _get_status_from_score(self, score: int) -> str:
        """Convert health score to status"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "warning"
        elif score >= 40:
            return "poor"
        else:
            return "critical"

    def _generate_recommendations(self, content_stats: Dict, read_stats: Dict) -> List[Dict[str, str]]:

        recommendations = []

        if content_stats["total_lockouts"] > 10:
            recommendations.append({
                "priority": "high",
                "title": "High Rate Limit Lockouts",
                "description": f"Consider reviewing rate limits. {content_stats['total_lockouts']} users currently locked out.",
                "action": "Review top limited content types and consider adjusting limits for legitimate users"
            })

        if len(read_stats["suspicious_ips"]) > 3:
            recommendations.append({
                "priority": "medium",
                "title": "Suspicious Read Patterns Detected",
                "description": f"{len(read_stats['suspicious_ips'])} IPs showing suspicious read behavior.",
                "action": "Consider implementing IP blocking for confirmed abusive IPs"
            })

        top_limited = max(content_stats["top_limited_content_types"].items(),
                         key=lambda x: x[1], default=(None, 0))
        if top_limited[1] > 50:
            recommendations.append({
                "priority": "low",
                "title": f"High Activity on {top_limited[0]}",
                "description": f"Content type '{top_limited[0]}' has high rate limiting activity.",
                "action": "Monitor for spam or consider if limits need adjustment"
            })

        if not recommendations:
            recommendations.append({
                "priority": "low",
                "title": "Rate Limiting Healthy",
                "description": "No immediate issues detected with rate limiting system.",
                "action": "Continue monitoring"
            })

        return recommendations

    def get_recent_alerts(self, hours: int = 24) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_alerts = [
            alert.__dict__ for alert in self.alerts
            if alert.timestamp > cutoff
        ]

        return sorted(recent_alerts, key=lambda x: x["timestamp"], reverse=True)

    def resolve_alert(self, alert_id: str) -> bool:
        # In a real implementation, you'd have alert IDs
        # For now, this is a placeholder
        return True

rate_limit_monitor = RateLimitMonitor()

async def run_rate_limit_monitoring():

    try:
        health_report = rate_limit_monitor.check_rate_limit_health()

        logger.info(
            "Rate limiting health check completed",
            health_score=health_report["health_score"],
            status=health_report["status"],
            active_users=health_report["content_rate_limits"]["active_users"],
            active_ips=health_report["read_rate_limits"]["active_ips"],
            total_lockouts=health_report["content_rate_limits"]["total_lockouts"]
        )

        if health_report["health_score"] < 60:
            logger.warning(
                "Rate limiting health score below threshold",
                health_score=health_report["health_score"],
                recommendations=health_report["recommendations"]
            )

        return health_report

    except Exception as e:
        logger.error(f"Rate limiting monitoring failed: {e}")
        return None
