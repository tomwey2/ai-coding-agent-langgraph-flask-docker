import os

from flask import Flask, flash, redirect, render_template, request, url_for

from extensions import db, scheduler
from models import AgentConfig


def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration from config.py
    app.config.from_object("config")

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Initialize extensions ---
    db.init_app(app)
    scheduler.init_app(app)

    # --- Routes ---
    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            config = AgentConfig.query.first()
            if not config:
                config = AgentConfig()
                db.session.add(config)

            config.task_app_base_url = request.form.get("task_app_base_url")
            config.agent_username = request.form.get("agent_username")
            config.agent_password = request.form.get("agent_password")
            config.target_project_id = request.form.get("target_project_id")
            polling_interval = int(request.form.get("polling_interval_seconds", 60))
            config.polling_interval_seconds = polling_interval
            config.is_active = "is_active" in request.form

            db.session.commit()

            # Reschedule job if interval changed
            if scheduler.get_job("agent_job"):
                scheduler.scheduler.reschedule_job(
                    "agent_job", trigger="interval", seconds=polling_interval
                )

            flash("Configuration saved successfully!", "success")
            return redirect(url_for("index"))

        config = AgentConfig.query.first()
        if not config:
            # Create a default, temporary config for the form if none exists
            config = AgentConfig(
                task_app_base_url="http://127.0.0.1:8000/api",
                agent_username="",
                agent_password="",
                target_project_id="",
                polling_interval_seconds=60,
                is_active=False,
            )

        return render_template("index.html", config=config)

    return app
