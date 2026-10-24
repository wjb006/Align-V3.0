FROM docker.io/opentripplanner/opentripplanner:2.8.0

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /var/opentripplanner
COPY start-otp.sh /usr/local/bin/start-otp.sh
RUN chmod +x /usr/local/bin/start-otp.sh
ENV JAVA_TOOL_OPTIONS="-Xmx4g"
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/start-otp.sh"]
