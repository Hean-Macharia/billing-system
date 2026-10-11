from app.models.service import ServiceType
from app.schemas.service import ServicePlanCreate


def test_service_type_accepts_common_names():
    assert ServiceType("internet") is ServiceType.INTERNET
    assert ServiceType("INTERNET") is ServiceType.INTERNET
    assert ServiceType("ftth") is ServiceType.FTTH
    assert ServiceType("FTTH") is ServiceType.FTTH


def test_service_plan_create_accepts_internet_service_type():
    plan = ServicePlanCreate(
        plan_code="PLAN-001",
        name="Fiber 20",
        service_type="internet",
        download_speed_mbps=20,
        upload_speed_mbps=10,
        base_price_kes=2500,
    )
    assert plan.service_type is ServiceType.INTERNET
