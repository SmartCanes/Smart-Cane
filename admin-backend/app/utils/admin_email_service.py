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
        sender_name   = os.environ.get("MAIL_SENDER_NAME", "iCane Smart Cane Admin")

        if not email_user or not email_pass:
            print("=" * 60)
            print("ADMIN OTP EMAIL (Console - configure SMTP for real emails)")
            print(f"TO:       {recipient_email}")
            print(f"OTP CODE: {otp_code}")
            print(f"EXPIRES:  5 minutes")
            print("=" * 60)
            return True

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
        return True

    except Exception as e:
        print(f"[ADMIN OTP] Failed to send to {recipient_email}: {e}")
        # Fallback — always print to console so dev can still test
        print("=" * 60)
        print("ADMIN OTP EMAIL (Fallback — SMTP failed)")
        print(f"TO:       {recipient_email}")
        print(f"OTP CODE: {otp_code}")
        print("=" * 60)
        return True


def send_admin_invite_email(recipient_email, login_link, temporary_username, admin_name=None):

    try:
        smtp_server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("MAIL_PORT", 587))
        email_user = os.environ.get("MAIL_USERNAME", "")
        email_pass = os.environ.get("MAIL_PASSWORD", "")
        sender_name = os.environ.get("MAIL_SENDER_NAME", "iCane Smart Cane Admin")

        if not email_user or not email_pass:
            print("=" * 60)
            print("ADMIN INVITE EMAIL (Console - configure SMTP for real emails)")
            print(f"TO:       {recipient_email}")
            print(f"USERNAME: {temporary_username}")
            print(f"LOGIN:    {login_link}")
            print("=" * 60)
            return {"ok": True}

        display_name = admin_name or "Admin"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "iCane Admin Account Invitation"
        msg["From"] = formataddr((sender_name, email_user))
        msg["To"] = recipient_email

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
                .box {{ margin: 16px 0; padding: 12px 14px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
                .button {{ display: inline-block; background: #1C253C; color: #fff !important; text-decoration: none; padding: 10px 16px; border-radius: 8px; font-weight: 600; }}
                .footer {{ background: #ddd; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>iCane: Smart Cane</h1>
                </div>
                <div class="content">
                    <h2>Admin Account Created</h2>
                    <p>Hello <strong>{display_name}</strong>,</p>
                    <p>Your admin account has been created. Please sign in and complete your first-time setup.</p>
                    <div class="box">
                        <p><strong>Temporary Username:</strong> {temporary_username}</p>
                        <p><strong>Login Link:</strong> <a href="{login_link}">{login_link}</a></p>
                    </div>
                    <p><a class="button" href="{login_link}">Go to Login</a></p>
                    <p>Best regards,<br>iCane Team</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 iCane. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""
iCane Admin Account Invitation

Hello {display_name},

Your admin account has been created. Please sign in and complete your first-time setup.

Temporary Username: {temporary_username}
Login Link: {login_link}

Best regards,
iCane Team
        """

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)

        print(f"[ADMIN INVITE] Email sent successfully to {recipient_email}")
        return {"ok": True}

    except Exception as e:
        print(f"[ADMIN INVITE] Failed to send to {recipient_email}: {e}")
        print("=" * 60)
        print("ADMIN INVITE EMAIL (Fallback — SMTP failed)")
        print(f"TO:       {recipient_email}")
        print(f"USERNAME: {temporary_username}")
        print(f"LOGIN:    {login_link}")
        print("=" * 60)
        return {"ok": False, "error": str(e)}