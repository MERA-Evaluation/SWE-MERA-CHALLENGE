FROM --platform=linux/amd64 rewive/swe-mera-challenge:spf13-cast-273

WORKDIR /testbed

RUN set -eu; \
    export GIT_TERMINAL_PROMPT=0; \
    git config --global --add safe.directory '*' 2>/dev/null || true; \
    rm -rf /patch /patches /solution /solutions /tests /gold /golden /results /task; \
    find /tools -mindepth 1 ! -name entrypoint -delete 2>/dev/null || true; \
    rm -f /usr/local/bin/apply-patch /usr/local/bin/eval-gold /usr/local/bin/eval-before \
          /usr/local/bin/eval-after /usr/local/bin/mcp-serve; \
    rm -rf /testbed/.git /testbed/.git_backup; \
    if [ -d /testbed/.github ]; then \
        find /testbed/.github -mindepth 1 -maxdepth 1 ! -name workflows \
             -exec rm -rf {} + 2>/dev/null || true; \
        find /testbed/.github -type f \
             ! -name '*.yml' ! -name '*.yaml' -delete 2>/dev/null || true; \
    fi; \
    find /testbed -maxdepth 6 \
         \( -name 'fix.patch' -o -name 'test.patch' -o -name 'tests.diff' \
            -o -name 'gold_patch*' -o -name 'golden*.patch' -o -name '*.orig' \
            -o -name '*.rej' \) -delete 2>/dev/null || true; \
    find / -maxdepth 3 \( -name '*.patch' -o -name '*.diff' \) \
         -not -path '/proc/*' -not -path '/sys/*' -not -path '/testbed/*' \
         -delete 2>/dev/null || true; \
    rm -rf /root/.cache /root/.composer/cache /tmp/* /var/tmp/* \
           /root/.bash_history /root/.viminfo /root/.python_history; \
    cd /testbed; \
    git init -q .; \
    git config user.email task@local; \
    git config user.name task; \
    git add -A; \
    git commit -q -m 'task snapshot' --no-verify; \
    git gc -q --prune=all 2>/dev/null || true

CMD ["sleep", "infinity"]
