# Inference image

Participants may change `Dockerfile`, `.dockerignore`, and add files required by
the Docker build.

The resulting image must:

- start the model server through its `ENTRYPOINT` and `CMD`;
- listen on `0.0.0.0:8000`;
- expose OpenAI-compatible `/v1/models` and `/v1/chat/completions` endpoints;
- serve the model ID declared in `../submission.yaml`;
- support OpenAI function tool calls.

The trusted `test.sh` waits for the server and verifies the model ID and a
single `bash` tool call. Participants must not modify it.
