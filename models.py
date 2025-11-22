from extensions import db


class AgentConfig(db.Model):
    __tablename__ = "agent_config"

    id = db.Column(db.Integer, primary_key=True)
    task_app_base_url = db.Column(db.String(255), nullable=False)
    agent_username = db.Column(db.String(100), nullable=True)
    agent_password = db.Column(
        db.String(255), nullable=True
    )  # Note: Storing passwords in plaintext is not secure!
    target_project_id = db.Column(db.String(50), nullable=True)
    polling_interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    is_active = db.Column(db.Boolean, nullable=False, default=False)

    def __init__(self, **kwargs):
        super(AgentConfig, self).__init__(**kwargs)

    def __repr__(self):
        return f"<AgentConfig {self.id}>"
