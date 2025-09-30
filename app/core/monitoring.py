import time
import logging
from datetime import datetime, timedelta, timezone
from typing import cast
from dataclasses import dataclass
from .content_rate_limiter import content_rate_limiter
from .rate_limit_decorator import read_rate_limiter

# Standard Python Logger
logger = logging.getLogger("monitoring")

@dataclass
class Alert:
    alert_type: str
    severity: str
    message: str
    details: dict[str, object]
    timestamp: datetime
    resolved: bool = False

class RateLimitMonitor:

    def __init__(self):
        self.alerts: list[Alert] = []
        self.alert_thresholds: dict[str, int] = {
            "burst_lockouts": 10,
            "daily_limit_hits": 5,
            "suspicious_patterns": 3,
            "read_abuse": 50
        }

    def check_rate_limit_health(self) -> dict[str, object]:
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

    def _analyze_content_rate_limits(self, hour_ago: float) -> dict[str, object]:
        # Lokale Counter und Collections
        active_users = 0
        lockouts_by_type: dict[str, int] = {}
        top_limited_content_types: dict[str, int] = {}
        user_tier_distribution: dict[str, int] = {"new": 0, "regular": 0, "established": 0, "trusted": 0}

        current_time = time.time()
        for lockout_key, lockout_time in content_rate_limiter.lockouts.items():
            if current_time < lockout_time:
                _user_id, content_type = lockout_key.split(":", 1)
                lockouts_by_type[content_type] = lockouts_by_type.get(content_type, 0) + 1

        for _user_id, content_attempts in content_rate_limiter.attempts.items():
            user_has_recent_activity = False

            for content_type, attempts in content_attempts.items():
                recent_attempts = [
                    (timestamp, count) for timestamp, count in attempts
                    if timestamp > hour_ago
                ]

                if recent_attempts:
                    user_has_recent_activity = True
                    top_limited_content_types[content_type] = \
                        top_limited_content_types.get(content_type, 0) + len(recent_attempts)

            if user_has_recent_activity:
                active_users += 1

        # Stats Dict am Ende zusammenbauen
        return {
            "active_users": active_users,
            "total_lockouts": len(content_rate_limiter.lockouts),
            "lockouts_by_type": lockouts_by_type,
            "burst_lockouts_1h": 0,
            "daily_limit_hits_1h": 0,
            "top_limited_content_types": top_limited_content_types,
            "user_tier_distribution": user_tier_distribution
        }

    def _analyze_read_rate_limits(self, hour_ago: float) -> dict[str, object]:
        active_ips = 0
        blocked_reads_1h = 0
        top_limited_endpoints: dict[str, int] = {}
        suspicious_ips: list[dict[str, object]] = []

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

                    top_limited_endpoints[endpoint_type] = \
                        top_limited_endpoints.get(endpoint_type, 0) + attempt_count

            if ip_has_recent_activity:
                active_ips += 1

                if ip_total_attempts > 500:
                    suspicious_ips.append({
                        "ip": ip,
                        "attempts_1h": ip_total_attempts,
                        "endpoints": list(endpoint_attempts.keys())
                    })

        # Stats Dict am Ende zusammenbauen
        return {
            "active_ips": active_ips,
            "blocked_reads_1h": blocked_reads_1h,
            "top_limited_endpoints": top_limited_endpoints,
            "suspicious_ips": suspicious_ips
        }

    def _check_for_alerts(self, content_stats: dict[str, object], read_stats: dict[str, object]) -> list[Alert]:
        alerts: list[Alert] = []
        now = datetime.now(timezone.utc)

        total_lockouts = content_stats.get("total_lockouts", 0)
        assert isinstance(total_lockouts, int)

        if total_lockouts > self.alert_thresholds["burst_lockouts"]:
            lockouts_by_type = content_stats.get("lockouts_by_type", {})
            alerts.append(Alert(
                alert_type="high_lockout_rate",
                severity="high",
                message=f"High number of rate limit lockouts: {total_lockouts}",
                details={"lockouts_by_type": lockouts_by_type},
                timestamp=now
            ))

        suspicious_ips = cast(list[dict[str, object]], read_stats.get("suspicious_ips", []))

        if len(suspicious_ips) > self.alert_thresholds["suspicious_patterns"]:
            alerts.append(Alert(
                alert_type="suspicious_read_patterns",
                severity="medium",
                message=f"Detected {len(suspicious_ips)} IPs with suspicious read patterns",
                details={"suspicious_ips": suspicious_ips[:5]},
                timestamp=now
            ))

        active_ips = read_stats.get("active_ips", 0)
        assert isinstance(active_ips, int)

        if active_ips > self.alert_thresholds["read_abuse"]:
            top_endpoints = read_stats.get("top_limited_endpoints", {})
            alerts.append(Alert(
                alert_type="read_abuse_spike",
                severity="medium",
                message=f"High number of IPs hitting read rate limits: {active_ips}",
                details={"top_endpoints": top_endpoints},
                timestamp=now
            ))

        self.alerts.extend(alerts)

        for alert in alerts:
            if alert.severity in ["high", "critical"]:
                logger.warning(
                    f"Rate limiting alert: {alert.message} (Type: {alert.alert_type}, " +
                    f"Severity: {alert.severity}, Details: {alert.details})"
                )

        return alerts

    def _calculate_health_score(self, content_stats: dict[str, object], read_stats: dict[str, object]) -> int:
        score = 100

        total_lockouts = content_stats.get("total_lockouts", 0)
        assert isinstance(total_lockouts, int)

        if total_lockouts > 20:
            score -= 30
        elif total_lockouts > 10:
            score -= 15
        elif total_lockouts > 5:
            score -= 5

        suspicious_ips = cast(list[dict[str, object]], read_stats.get("suspicious_ips", []))
        suspicious_count = len(suspicious_ips)

        if suspicious_count > 10:
            score -= 25
        elif suspicious_count > 5:
            score -= 15
        elif suspicious_count > 2:
            score -= 5

        active_ips = read_stats.get("active_ips", 0)
        assert isinstance(active_ips, int)

        if active_ips > 100:
            score -= 20
        elif active_ips > 50:
            score -= 10

        return max(0, score)

    def _get_status_from_score(self, score: int) -> str:
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

    def _generate_recommendations(self, content_stats: dict[str, object], read_stats: dict[str, object]) -> list[dict[str, str]]:
        recommendations: list[dict[str, str]] = []

        total_lockouts = content_stats.get("total_lockouts", 0)
        assert isinstance(total_lockouts, int)

        if total_lockouts > 10:
            recommendations.append({
                "priority": "high",
                "title": "High Rate Limit Lockouts",
                "description": f"Consider reviewing rate limits. {total_lockouts} users currently locked out.",
                "action": "Review top limited content types and consider adjusting limits for legitimate users"
            })

        suspicious_ips = cast(list[dict[str, object]], read_stats.get("suspicious_ips", []))
        suspicious_count = len(suspicious_ips)

        if suspicious_count > 3:
            recommendations.append({
                "priority": "medium",
                "title": "Suspicious Read Patterns Detected",
                "description": f"{suspicious_count} IPs showing suspicious read behavior.",
                "action": "Consider implementing IP blocking for confirmed abusive IPs"
            })

        top_limited_content = cast(dict[str, int], content_stats.get("top_limited_content_types", {}))

        if top_limited_content:
            max_item = max(top_limited_content.items(), key=lambda x: x[1])
            top_content_type, top_count = max_item

            if top_count > 50:
                recommendations.append({
                    "priority": "low",
                    "title": f"High Activity on {top_content_type}",
                    "description": f"Content type '{top_content_type}' has high rate limiting activity.",
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

    def get_recent_alerts(self, hours: int = 24) -> list[dict[str, object]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_alerts = [
            alert.__dict__ for alert in self.alerts
            if alert.timestamp > cutoff
        ]

        return sorted(recent_alerts, key=lambda x: cast(datetime, x["timestamp"]), reverse=True)

    def resolve_alert(self, _alert_id: str) -> bool:
        # In a real implementation, you'd have alert IDs
        # For now, this is a placeholder
        return True

rate_limit_monitor = RateLimitMonitor()

async def run_rate_limit_monitoring() -> dict[str, object] | None:
    try:
        health_report = rate_limit_monitor.check_rate_limit_health()
        content_limits = cast(dict[str, object], health_report['content_rate_limits'])
        read_limits = cast(dict[str, object], health_report['read_rate_limits'])
        health_score = cast(int, health_report["health_score"])

        logger.info(
            f"Rate limiting health check completed - " +
            f"Health Score: {health_report['health_score']}, " +
            f"Status: {health_report['status']}, " +
            f"Active Users: {content_limits['active_users']}, " +
            f"Active IPs: {read_limits['active_ips']}, " +
            f"Total Lockouts: {content_limits['total_lockouts']}"
        )

        if health_score < 60:
            logger.warning(
                f"Rate limiting health score below threshold: {health_report['health_score']} - " +
                f"Recommendations: {health_report['recommendations']}"
            )

        return health_report

    except Exception as e:
        logger.error(f"Rate limiting monitoring failed: {e}")
        return None
