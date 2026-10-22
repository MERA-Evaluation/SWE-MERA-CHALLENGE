ARG VLLM_VERSION=0.31.0
FROM vllm/vllm-openai:v${VLLM_VERSION}

ENV FLASHINFER_CUDA_ARCH_LIST=12.0a \
    HF_HOME=/opt/huggingface

# Bake the model weights into the image so the runtime does not download them.
RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3.5-9B', local_dir='/models/Qwen3.5-9B')"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000

ENTRYPOINT ["vllm", "serve"]
CMD ["/models/Qwen3.5-9B", "--host", "0.0.0.0", "--port", "8000", "--api-key", "dummy", "--attention-backend", "flashinfer", "--block-size", "256", "--enable-prefix-caching", "--enable-prompt-tokens-details", "--kv-cache-dtype", "fp8", "--max-model-len", "65536", "--max-num-seqs", "512", "--reasoning-parser", "qwen3", "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_xml", "--served-model-name", "qwen35-9b-chat", "--data-parallel-size", "3", "--trust-remote-code"]
