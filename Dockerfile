FROM python:3.13-slim

ADD peak_assistant /app/peak_assistant
WORKDIR /app
ADD *.sh /app/
ADD pyproject.toml /app/
ADD README.md /app/README.md
ADD docker-startup.sh /app/docker-startup.sh
ADD generate_certificates.sh /app/generate_certificates.sh
RUN chmod +x /app/*.sh

RUN useradd peakassistant
RUN mkdir /home/peakassistant && chown peakassistant:peakassistant /home/peakassistant
RUN mkdir /certs/ && chown peakassistant:peakassistant /certs/
USER peakassistant
RUN python -m pip install . && rm -rf ${HOME}/.cache
WORKDIR /home/peakassistant
ENV PATH="/home/peakassistant/.local/bin:${PATH}"
ENTRYPOINT ["/app/docker-startup.sh"]
