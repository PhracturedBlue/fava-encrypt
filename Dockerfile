ARG FOREGO_VERSION=v0.17.0
ARG GOLANG_VERSION=1.16.7
# ARG LEDGER_DIR=/ledger
# ARG ENCRYPTED_DIR=/secure
# ARG PIP-MODULES
# Use a specific version of golang to build both binaries
FROM golang:$GOLANG_VERSION as gobuilder

# Build forego from scratch
FROM gobuilder as forego

ARG FOREGO_VERSION

RUN git clone https://github.com/nginx-proxy/forego/ \
   && cd /go/forego \
   && git -c advice.detachedHead=false checkout $FOREGO_VERSION \
   && go mod download \
   && CGO_ENABLED=0 GOOS=linux go build -o forego . \
   && go clean -cache \
   && mv forego /usr/local/bin/ \
   && cd - \
   && rm -rf /go/forego



FROM debian:bullseye as pybuild
RUN apt-get update && apt-get install -y \
        pip build-essential curl python3-venv git && \
    curl -fsSL https://deb.nodesource.com/setup_16.x | bash - && \
    apt install nodejs && \
    rm -rf /var/lib/apt/lists/*
RUN pip install tox aiohttp cryptography
ARG FAVA_GIT_REPO
RUN if [ x"$FAVA_GIT_REPO" != "x" ]; then \
      cd /tmp && git clone --depth 1 -b $(echo $FAVA_GIT_REPO | sed -e 's/.*@//') $(echo $FAVA_GIT_REPO | sed -e 's/@.*//') && \
      cd fava && (cd frontend && npm ci && npm run build) && tox -e build-dist && \
      pip install /tmp/fava/dist/*.whl; \
      cd && rm -rf /tmp/fava; \
    else \
      pip install fava; \
    fi
ARG PIP_MODULES
RUN pip install aiohttp cryptography inotify && \
    if [ x"${PIP_MODULES}" != "x" ]; then pip install ${PIP_MODULES}; fi

FROM debian:bullseye-slim
COPY --from=forego /usr/local/bin/forego /usr/local/bin/forego
COPY --from=pybuild /usr/local/ /usr/local/
RUN mkdir /secure

RUN apt-get update && apt-get install -y \
        fuse nginx securefs python3 python3-pkg-resources nano && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash fava
ARG LEDGER_DIR=/ledger
ARG ENCRYPTED_DIR=/secure
ARG KEEP_OPEN=300
ARG NGINX_PORT_REDIRECT=off
RUN mkdir /ledger /tmp/.beancount
RUN chown -R fava /ledger/ /tmp/.beancount
COPY Procfile listener.py auth.token fava_wrap.py /app/
COPY nginx.conf /etc/nginx/nginx.conf
RUN sed -i -e "s|LEDGER_DIR|${LEDGER_DIR}|g" -e "s|ENCRYPTED_DIR|${ENCRYPTED_DIR}|" -e "s|KEEP_OPEN|${KEEP_OPEN}|" /app/Procfile
RUN sed -i -e "s/port_in_redirect off/port_in_redirect ${NGINX_PORT_REDIRECT}/" /etc/nginx/nginx.conf
RUN sed -i -e "s|WATCH_DIR =.*|WATCH_DIR = '${LEDGER_DIR}'|" /app/fava_wrap.py
WORKDIR /app
EXPOSE 5000
ENV PYTHONUNBUFFERED=1
CMD ["forego", "start", "-r"]
