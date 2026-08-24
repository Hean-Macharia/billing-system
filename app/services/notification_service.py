async def send_sms(
    phone: str,
    message: str,
):
    """
    SMS provider will be integrated later.
    """

    return {
        "status": "simulation",
        "phone": phone,
        "message": message,
    }


async def send_email(
    email: str,
    subject: str,
    message: str,
):
    """
    Email provider will be integrated later.
    """

    return {
        "status": "simulation",
        "email": email,
        "subject": subject,
    }