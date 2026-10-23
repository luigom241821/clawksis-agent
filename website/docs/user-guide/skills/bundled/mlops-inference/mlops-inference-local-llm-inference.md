---
title: "Local Llm Inference — Run and serve local LLMs with llama.cpp, vLLM and HF"
sidebar_label: "Local Llm Inference"
description: "Run and serve local LLMs with llama.cpp, vLLM and HF"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Local Llm Inference

Run and serve local LLMs with llama.cpp, vLLM and HF.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/mlops-inference/local-llm-inference` |
| Version | `1.0.0` |
| Author | Clawksis (consolidated) |
| License | MIT |
| Platforms | linux, macos |
| Tags | `llm`, `inference`, `serving`, `quantization`, `llama-cpp`, `vllm`, `huggingface`, `models`, `abliteration`, `evaluation` |
| Related skills | [`local-llm-hardware`](../../bundled/mlops-inference/mlops-inference-local-llm-hardware.md), [`model-fallback`](../../bundled/model-fallback/model-fallback-model-fallback.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Local LLM Inference & Model Management

> **Umbrella skill** — covers running models locally (llama.cpp), high-throughput serving (vLLM), model management (HuggingFace Hub), abliteration (obliteratus), and model discovery/evaluation. Each subtopic has a detailed reference file.

## Quick Start

```bash
# Which tool to use?
# llama.cpp:     single-user local inference, GGUF format, CPU/GPU
# vLLM:          multi-user serving, OpenAI-compatible API, production
# obliteratus:   remove refusals from a model (diff-in-means)
# hf (Hub CLI):  download/upload models, datasets, Spaces
# model-discovery: research models by name, compare specs
```

## Subtopic References

| Topic | Reference | What It Covers |
|-------|-----------|----------------|
| **llama.cpp** | `references/llama-cpp.md` | GGUF inference, quantization, Python bindings, CLI, server mode |
| **vLLM** | `references/vllm.md` | High-throughput serving, OpenAI API, quantization, multi-GPU |
| **Obliteratus** | `references/obliteratus.md` | Abliterate refusals via diff-in-means, before/after comparison |
| **HuggingFace Hub** | `references/huggingface-hub.md` | `hf` CLI: search, download, upload models/datasets/Spaces |
| **Model Discovery** | `references/model-discovery.md` | Find models by name/capability, read config.json for architecture |
| **Model Evaluation** | `references/llm-evaluation.md` | lm-eval-harness benchmarks (MMLU, GSM8K), W&B experiment tracking |
