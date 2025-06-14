import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@jolym.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

def send_email(to_email, subject, html_content):
    """
    Send an email with the given parameters.
    
    Args:
        to_email (str): Recipient email address
        subject (str): Email subject
        html_content (str): HTML content of the email
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured. Email would be sent to: " + to_email)
        logger.info(f"Email subject: {subject}")
        logger.info(f"Reset link would point to: {FRONTEND_URL}/reset-password")
        # For development, return True to simulate successful email sending
        return True
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        
        # Attach HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, message.as_string())
            
        logger.info(f"Email sent successfully to {to_email}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}", exc_info=True)
        return False

def send_password_reset_email(to_email, reset_token):
    """
    Send a password reset email with a reset link.
    
    Args:
        to_email (str): Recipient email address
        reset_token (str): Password reset token
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    
    subject = "Reset Your Password - Jolym"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #10b981; color: white; padding: 10px 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .button {{ display: inline-block; background-color: #10b981; color: white; text-decoration: none; padding: 10px 20px; border-radius: 4px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Password Reset Request</h1>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>We received a request to reset your password for your Jolym account. To reset your password, click the button below:</p>
                <p style="text-align: center;">
                    <a href="{reset_link}" class="button">Reset Password</a>
                </p>
                <p>If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>
                <p>This link will expire in 30 minutes for security reasons.</p>
                <p>If the button above doesn't work, copy and paste the following link into your browser:</p>
                <p>{reset_link}</p>
            </div>
            <div class="footer">
                <p>&copy; {2024} Jolym. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email(to_email, subject, html_content)