# The judge needs Linux: it relies on rlimits and os.wait4, and links with
# -static. On macOS or Windows, run it in here instead.
#
#   docker build -t terasering .
#   docker run --rm -it -v "$PWD":/work terasering
#
# The bind mount keeps problems/ and examples/ on the host, so they can be
# edited normally and tracked in git.

# Ubuntu 24.04 ships GCC 13, the first release that accepts -std=c++23 under
# that name instead of falling back to c++2b.
FROM ubuntu:24.04

# Without this, tzdata stops the build to ask for a timezone.
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Install into a virtualenv so pip is not fighting the system Python, which
# Ubuntu marks as externally managed.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY pyproject.toml README.md ./
COPY terasering ./terasering

RUN pip install --upgrade pip && pip install -e ".[dev]"

# Probe the compiler now rather than during the first submission. This also
# fails the build immediately if the toolchain cannot produce C++23.
RUN python3 -c "from terasering import CPP; from terasering.compiler import Compiler; \
print('C++ standard:', Compiler(CPP).standard)"

CMD ["bash"]
