# Worked case: Qwen3.8-27B-OBLITERATED on rented GPU

This is a worked deployment and cost comparison, not a permanent price list. Re-check provider offers and model pages before provisioning.

## Artifact evidence

Source: https://huggingface.co/OBLITERATUS/Qwen3.8-27B-OBLITERATED

The model card identifies an Apache-2.0 Qwen3.8 27B derivative with these files:

- `Qwen3.8-27B-OBLITERATED-Q4_K_M.gguf`: approximately 15GB;
- `IQ4_XS`: approximately 14GB;
- `Q5_K_M`: approximately 18GB;
- `Q6_K`: approximately 21GB;
- `Q8_0`: approximately 27GB;
- BF16 Transformers weights: approximately 50GB across shards;
- MLX 4-bit: approximately 14GB for Apple Silicon.

The card reports zero hard refusals across its own 842-prompt evaluation, 81.4% MMLU versus 87.4% for stock Qwen3.8-27B, and one empty response in an 80-query skeptic battery. These are self-reported results, not independent validation.

The card's recommended generation settings are unusually specific:

```text
temperature: 0
repetition_penalty: 1.15
max_new_tokens: at least 2048
system prompt: empty or none
enable_thinking: off by default
do_sample: false
```

Treat these as a starting point for a smoke test. Do not infer tool calling, vision, or Hermes compatibility from the uncensored claim; the card primarily documents text generation and GGUF/MLX/Transformers use.

## HF execution finding

The repository page exposes model files and a Deploy surface, but no verified free Hugging Face browser inference path was visible during review. A Hub repository is not an execution service. If no Inference Provider is listed, the real options are a local runtime, a paid HF compute product, a rented GPU, or a separate API provider.

## Hardware decision

A Q4 file around 14–15GB is a good starting point for a 24GB GPU. The extra VRAM is needed for the runtime, KV cache, context, and batching. A 23–24GB CPU-only machine is not equivalent: it may load a small IQ4 quant with a low context, but it has little memory headroom and is not a practical 27B serving target without a measured benchmark.

In the evaluated control VM, the observed preflight was:

```text
architecture: aarch64
CPU: 4 vCPU
RAM: 23 GiB
NVIDIA GPU: none visible (`nvidia-smi` absent)
free disk: about 23GB
Vast instances: none active
```

This observation is session-specific. Always repeat the preflight on the actual inference target; the VM can still act as a control plane while the model runs remotely.

## Vast-versus-API calculation

Sources:

- Vast pricing: https://vast.ai/pricing
- Model API page: https://www.orcarouter.ai/models/obsidian/qwen3.8-27b

At review time, the model API page showed `$0.40 / 1M` input tokens and `$4.21 / 1M` output tokens. Vast's public pricing is supply/demand based; the working 4090 range observed in the existing Vast workflow was roughly `$0.65–$0.71/h`, with storage around `$0.04–$0.05/h` per 100GB and interruptible offers often materially cheaper. Treat those numbers as indicative and query live offers.

Including `$0.045/h` storage, the output-only break-even is approximately:

```text
($0.65 + $0.045) / $4.21M = 45.9 output tokens/s
($0.71 + $0.045) / $4.21M = 49.8 output tokens/s
```

That only favors Vast if the GPU is kept busy and the local quant actually sustains the required throughput. For an intermittent session of 100k input plus 20k output tokens, the API calculation is `$0.1242`, while a full rented hour is about `$0.70–$0.76` before retries and setup. Heavy continuous use reverses the result; short chats do not.

## Recommended deployment shape

For the exact uncensored artifact and no router token credits:

1. Rent a 24GB GPU, preferably a 4090; use interruptible capacity only if preemption is acceptable.
2. Run the Q4_K_M GGUF with llama.cpp or Ollama on the GPU host.
3. Keep the ARM VM as the control plane.
4. Connect through a private SSH/Tailscale path to an OpenAI-compatible `llama-server` endpoint.
5. Smoke-test a completion, memory usage, context behavior, and any tool-call format before wiring Hermes.
6. Destroy the instance after use; stopping it may leave storage charges.

Use the derivative as a separate endpoint until tool calling, JSON adherence, repetition behavior, and context limits are verified. A model with removed refusals is not automatically a reliable agent model.
