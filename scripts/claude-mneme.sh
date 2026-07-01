#!/usr/bin/env bash
set -euo pipefail

# Claude Code inherits HTTP_PROXY/HTTPS_PROXY from the shell. If those point to
# an inactive local proxy, Claude cannot connect to either Anthropic or Mneme.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
export NO_PROXY="127.0.0.1,localhost,::1${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

exec claude "$@"
