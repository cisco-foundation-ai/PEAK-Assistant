FROM python:3.13-slim

# MCP servers commonly need NodeJS and npm/npx, so make sure 
# they are installed. Do it early for better layer caching.
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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
ENV PATH="/home/peakassistant/.local/bin:${PATH}"
RUN python -m pip install . && rm -rf ${HOME}/.cache
WORKDIR /home/peakassistant
ENTRYPOINT ["/app/docker-startup.sh"]
