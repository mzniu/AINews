from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount


def test_publish_job_defaults():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    account = PublisherAccount(
        id="acc1",
        platform="wechat_channels",
        nickname="测试号",
        platform_uid="uid1",
        session_path="data/publish/sessions/acc1.enc",
    )
    session.add(account)
    job = PublishJob(id="job1", account_id="acc1", video_path="data/videos/a.mp4", title="标题")
    session.add(job)
    session.commit()
    row = session.get(PublishJob, "job1")
    assert row.status == "pending"
    assert row.retry_count == 0
