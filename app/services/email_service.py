import os
from typing import Protocol

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException


class HtmlContentGenerator(Protocol):
    def __call__(self, *, recipient_name: str) -> str: ...


BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@plaetzchen.xyz")
FROM_NAME = os.getenv("FROM_NAME", "Plätzchen Community")


class EmailService:
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> bool:
        if not BREVO_API_KEY:
            print(f"📧 [DEV MODE] Email would be sent to {to_email}")
            print(f"📧 [DEV MODE] Subject: {subject}")
            print(f"📧 [DEV MODE] Body preview: {html_content[:200]}...")
            return True

        try:
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key["api-key"] = BREVO_API_KEY
            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                sib_api_v3_sdk.ApiClient(configuration)
            )

            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": to_email}],
                sender={
                    "name": from_name or FROM_NAME,
                    "email": from_email or FROM_EMAIL,
                },
                subject=subject,
                html_content=html_content,
            )

            api_response = api_instance.send_transac_email(send_smtp_email)
            print(f"✅ Email sent successfully to {to_email}: {api_response}")
            return True

        except ApiException as e:
            print(f"❌ Failed to send email via Brevo to {to_email}: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error sending email to {to_email}: {e}")
            return False

    @staticmethod
    def send_bulk_emails(
        recipients: list[dict[str, str]],
        subject: str,
        html_content_generator: HtmlContentGenerator,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> dict[str, int]:
        results = {"success": 0, "failed": 0}

        for recipient in recipients:
            try:
                html_content = html_content_generator(
                    recipient_name=recipient.get("name", "Community-Mitglied")
                )

                success = EmailService.send_email(
                    to_email=recipient["email"],
                    subject=subject,
                    html_content=html_content,
                    from_email=from_email,
                    from_name=from_name,
                )

                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                print(
                    f"❌ Error sending email to {recipient.get('email', 'unknown')}: {e}"
                )
                results["failed"] += 1

        return results
