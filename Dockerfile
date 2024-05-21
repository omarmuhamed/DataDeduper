FROM python:3.7-slim
ENV APP_HOME /dashboard
ENV PYTHONUNBUFFERED 1
ENV FLASK_ENV development
ENV FLASK_DEBUG 1
ENV DEBUG TRUE
ARG options
ENV OPTIONS $options
WORKDIR $APP_HOME
COPY . ./
RUN pip install -r requirements.txt
CMD exec gunicorn $OPTIONS -b :$PORT --workers 4 --timeout 600 --threads 2 -k gthread --log-level 'debug' --error-logfile /gunicorn-logs/error.log --access-logfile /gunicorn-logs/access.log 'app:create_app()'
