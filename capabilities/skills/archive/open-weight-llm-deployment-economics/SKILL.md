---
name: open-weight-llm-deployment-economics
description: "Use when choosing how to run open-weight LLMs."
version: 1.0.0
author: W.Alter
license: MIT
tags: [open-weight, llm, inference, gguf, ollama, llama-cpp, vast, huggingface, cost]
metadata:
  hermes:
    tags: [open-weight, llm, inference, gguf, ollama, llama-cpp, vast, huggingface, cost]
    related_skills: [vastai-gpu-workflow, llama-cpp, huggingface-hub, model-id-lookup]
---

# Open-Weight LLM Deployment Economics

Use this skill when Monsieur asks where or how to run an open-weight language model—local hardware, a rented GPU, Hugging Face infrastructure, or a token API—especially when the model is quantized, uncensored/abliterated, or intended to sit behind Hermes.

## When to Use

Load this skill for open-weight LLM hosting choices, GGUF/MLX sizing, Hugging Face execution questions, Vast.ai versus token-API comparisons, remote Ollama/llama.cpp serving, and deciding whether a model is suitable for Hermes tools.

## Core decision rule

Do not confuse **model hosting** with **model execution**:

- Hugging Face Hub stores weights and metadata.
- An Inference Provider or API executes the model and bills by token or request.
- An Inference Endpoint, Job, or GPU Space executes the model on rented compute and bills infrastructure.
- Local Ollama/llama.cpp executes the model on the user's hardware.
- Vast.ai executes the model on a temporary rented GPU and bills wall-clock time plus storage.

If a model page exposes files but no usable Inference Provider, never promise browser execution. Read the actual page and identify the execution path before recommending it.

## Workflow

### 1. Identify the exact artifact

Record the exact repository, revision, architecture, and format. Distinguish:

- original/aligned checkpoint;
- abliterated or uncensored derivative;
- Transformers safetensors;
- GGUF for llama.cpp/Ollama;
- MLX for Apple Silicon;
- quantization and exact file size;
- whether vision, tool calling, and structured output are actually documented.

Treat claims such as “zero refusals” or “uncensored” as model-card claims, not independent capability proof. A derivative may remove refusals while losing reasoning quality, tool reliability, or multimodal support.

### 2. Preflight the target machine

Before pricing or installing, inspect the actual target:

```bash
uname -m
nproc
free -h
df -h /
nvidia-smi
```

Record GPU model/VRAM, system RAM, CPU architecture, free disk, and whether the CUDA/Metal/ROCm runtime is visible. A CPU-only ARM VM with a few vCPUs is normally a control plane, not a practical host for a 27B model, even if a small quantized file technically fits on disk.

For a 27B model, use the repository's Q4 quant as the starting point. A roughly 14–15GB Q4 GGUF normally wants a 24GB GPU for usable headroom. Include runtime allocations, KV cache, context length, batching, and auxiliary projectors; file size is not the complete VRAM requirement.

### 3. Choose the execution path

Use this default matrix:

| Usage pattern | Default path |
|---|---|
| Occasional short chats | Token API, if an exact provider exists |
| Several hours of heavy generation | On-demand or interruptible rented GPU |
| Privacy, custom weights, arbitrary adapters | Local or rented GPU |
| No payment method and no suitable local GPU | Look for a genuine free hosted provider; do not relabel paid HF compute as free |
| Hermes agent with tools | Separate endpoint first; verify tool calls before replacing the primary model |

For a remote deployment, keep the existing CPU VM as the control plane and run `llama-server` or Ollama on the GPU host. Expose the OpenAI-compatible endpoint privately through SSH/Tailscale; never expose an unauthenticated inference port to the public Internet.

### 4. Compare the economics honestly

Use the provider's live price immediately before provisioning. Include:

- GPU hourly rate and whether the offer is interruptible;
- persistent disk while stopped;
- model download and warm-up time;
- idle time between requests;
- retries, preemption, and failed generations;
- setup/maintenance time;
- API input and output token prices;
- the actual wall-clock throughput of the chosen quant and context length.

For a token API:

```text
api_cost = input_tokens / 1,000,000 * input_price
         + output_tokens / 1,000,000 * output_price
```

For a rented GPU:

```text
gpu_cost = paid_hours * (gpu_hourly_rate + storage_hourly_rate)
         + download_or_setup_cost
         + retry_cost
```

For output-heavy comparisons, the rough break-even throughput is:

```text
required_output_tok_per_second
  = (gpu_hourly_rate + storage_hourly_rate)
    / output_price_per_million * 1,000,000 / 3,600
```

This threshold is meaningful only if the GPU stays busy. A one-hour rental for a few short prompts is usually more expensive than a token API, even when the raw GPU rate looks cheap.

### 5. Use Vast.ai safely

When Vast is the chosen path:

1. Search live offers immediately before creation; do not hard-code historical offer IDs or prices.
2. Prefer a 24GB GPU for Q4 27B GGUF and an interruptible offer only when preemption is acceptable.
3. Use the smallest disk that leaves room for the model, runtime, logs, and temporary files.
4. Put the model and serving command in a reusable template only after one clean pilot.
5. Smoke-test the OpenAI-compatible endpoint with a real completion before connecting Hermes.
6. Measure cold start, warm throughput, VRAM, RAM, and context behavior.
7. **Destroy** the instance when finished; stopping it may continue storage billing.

Do not recommend the cheapest host solely by advertised dollars per hour. Check reliability, GPU verification, disk, network, and interruption risk.

### 6. Verify agent suitability separately

A model that produces unrestricted text is not automatically a good Hermes model. Verify:

- chat template and role handling;
- tool-call serialization and multi-turn tool results;
- JSON/schema adherence;
- context-window behavior;
- reasoning/thinking controls;
- output repetition and stop behavior;
- safety boundary appropriate to the intended use.

Keep an uncensored derivative as a separate endpoint until these checks pass. Do not silently replace the main Hermes model.

## Pitfalls

- “From Hugging Face” may mean downloading weights, not free remote inference.
- A Hugging Face Deploy button can create a paid endpoint; it is not a free loophole around API credits.
- A 14–15GB GGUF on a 23–24GB RAM CPU machine is not equivalent to a 24GB GPU deployment.
- Smaller quantization reduces memory pressure but may reduce coding/reasoning quality; do not compare quality from file size alone.
- A hosted model's reported tokens/sec is not a benchmark for a rented local quant.
- A model card's refusal benchmark is self-reported; record it as evidence, not fact beyond the card.
- Never put a public unauthenticated `llama-server` or Ollama port on the Internet.

## Reference

See `references/qwen38-27b-obliterated-case.md` for the validated Qwen3.8 worked example, hardware preflight, model-card settings, and API-versus-Vast break-even calculation.
