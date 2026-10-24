FROM docker.io/opentripplanner/opentripplanner:2.8.0

USER root
WORKDIR /var/opentripplanner
COPY start-otp.sh /usr/local/bin/start-otp.sh
RUN chmod +x /usr/local/bin/start-otp.sh
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/start-otp.sh"]
