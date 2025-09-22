# Copyright (c) 2025 Cisco Systems, Inc. and its affiliates
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

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
EXPOSE 8501/tcp
ENTRYPOINT ["/app/docker-startup.sh"]
