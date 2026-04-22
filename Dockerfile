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

# Pull Node 20 binaries from the official signed image.
# Both node:20-slim and python:3.13-slim are Debian Bookworm based,
# so the binaries are compatible without needing to run curl | bash.
FROM node:20-slim AS node

FROM python:3.13-slim

# Copy Node 20 and npm/npx from the official image.
# MCP servers that use npx (e.g. @modelcontextprotocol/server-*) require Node.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

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
