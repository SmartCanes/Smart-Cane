import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr


def send_admin_otp_email(recipient_email, otp_code, admin_name=None):

    try:
        smtp_server   = os.environ.get("MAIL_SERVER",      "smtp.gmail.com")
        smtp_port     = int(os.environ.get("MAIL_PORT",    587))
        email_user    = os.environ.get("MAIL_USERNAME",    "")
        email_pass    = os.environ.get("MAIL_PASSWORD",    "")
        sender_name   = os.environ.get("MAIL_SENDER_NAME", "iCane Smart Cane")

        if not email_user or not email_pass:
            msg = "Mail configuration is missing. Set MAIL_USERNAME and MAIL_PASSWORD."
            print(f"[ADMIN OTP] {msg}")
            return {"ok": False, "error": msg}

        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "iCane Admin — Email Verification"
        msg["From"]    = formataddr((sender_name, email_user))
        msg["To"]      = recipient_email

        display_name = admin_name or "Admin"

        # HTML content – matching guardian email design
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1C253C; color: white; padding: 20px; text-align: center; }}
                .content {{ background: #f9f9f9; padding: 30px; }}
                .otp-code {{ 
                    font-size: 32px; 
                    font-weight: bold; 
                    text-align: center; 
                    color: #1C253C;
                    letter-spacing: 5px;
                    margin: 20px 0;
                    padding: 15px;
                    background: white;
                    border-radius: 8px;
                    border: 2px dashed #1C253C;
                }}
                .footer {{ 
                    background: #ddd; 
                    padding: 15px; 
                    text-align: center; 
                    font-size: 12px; 
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>iCane: Smart Cane</h1>
                </div>
                <div class="content">
                    <h2>Admin Email Verification</h2>
                    <p>Hello <strong>{display_name}</strong>,</p>
                    <p>
                        Your email has been use in our system. Please verify your email using the OTP below:
                    </p>

                    <div class="otp-code">{otp_code}</div>

                    <p>This verification code expires in <strong>5 minutes</strong>.</p>

                    <p>If you didn't request this, kindly ignore it.</p>

                    <p>Best regards,<br>iCane Team</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 iCane. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Plain text fallback (matching the new design's content)
        text_content = f"""
iCane: Smart Cane - Email Verification

Hello {display_name},

Your email has been use in our system. Please verify your email using the OTP below:

OTP CODE: {otp_code}

This code expires in 5 minutes.

If you didn't request this, just kindly ignore it.

Best regards,
iCane Team
        """

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content,  "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)

        print(f"[ADMIN OTP] Email sent successfully to {recipient_email}")
        return {"ok": True, "error": None}

    except Exception as e:
        err = str(e)
        print(f"[ADMIN OTP] Failed to send to {recipient_email}: {err}")
        return {"ok": False, "error": err}


def send_admin_invite_email(recipient_email, login_link, temporary_username, admin_name=None):
    try:
        smtp_server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("MAIL_PORT", 587))
        email_user = os.environ.get("MAIL_USERNAME", "")
        email_pass = os.environ.get("MAIL_PASSWORD", "")
        sender_name = os.environ.get("MAIL_SENDER_NAME", "iCane Smart Cane")

        if not email_user or not email_pass:
            msg = "Mail configuration is missing. Set MAIL_USERNAME and MAIL_PASSWORD."
            print(f"[ADMIN INVITE] {msg}")
            return {"ok": False, "error": msg}

        display_name = admin_name or "Admin"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "iCane Admin - Account Invitation"
        msg["From"] = formataddr((sender_name, email_user))
        msg["To"] = recipient_email

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset=\"utf-8\">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1C253C; color: white; padding: 20px; text-align: center; }}
                .content {{ background: #f9f9f9; padding: 30px; }}
                .box {{ background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 14px; margin: 18px 0; }}
                .button {{ display: inline-block; padding: 12px 18px; background: #1C253C; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; }}
                .footer {{ background: #ddd; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class=\"container\">
                <div class=\"header\">
                    <h1>iCane: Smart Cane</h1>
                </div>
                <div class=\"content\">
                    <h2>Admin Account Invitation</h2>
                    <p>Hello <strong>{display_name}</strong>,</p>
                    <p>You were invited to access the iCane Admin panel. Use your temporary credentials to log in.</p>
                    <div class=\"box\">
                        <p style=\"margin:0;\"><strong>Temporary Username:</strong> {temporary_username}</p>
                        <p style=\"margin:8px 0 0;\">Temporary Password: use the password provided by your Super Admin.</p>
                    </div>
                    <p>After your first login, a verification OTP will be sent to this email before you can set your new username and password.</p>
                    <p><a class=\"button\" href=\"{login_link}\">Open Admin Login</a></p>
                    <p>If the button does not work, open this link in your browser:<br><a href=\"{login_link}\">{login_link}</a></p>
                </div>
                <div class=\"footer\">&copy; 2026 iCane. All rights reserved.</div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
iCane Admin Account Invitation

Hello {display_name},

You were invited to access the iCane Admin panel.

Temporary Username: {temporary_username}
Temporary Password: use the password provided by your Super Admin.

Login here: {login_link}

After first login, an OTP will be sent to your email before you can set your new username and password.
        """

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)

        print(f"[ADMIN INVITE] Email sent successfully to {recipient_email}")
        return {"ok": True, "error": None}
    except Exception as e:
        err = str(e)
        print(f"[ADMIN INVITE] Failed to send to {recipient_email}: {err}")
        return {"ok": False, "error": err}