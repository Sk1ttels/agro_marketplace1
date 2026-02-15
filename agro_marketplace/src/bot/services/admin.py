from config import settings

async def is_admin(user_id: int) -> bool:
    # settings.ADMIN_IDS може бути list[int] або list[str] залежно від env — страхуємось
    try:
        admins = [int(x) for x in (settings.ADMIN_IDS or [])]
    except Exception:
        admins = []
    return int(user_id) in admins
