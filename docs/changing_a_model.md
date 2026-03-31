# 更改 CodeMind 使用的模型 (Changing a Model)

CodeMind 默认支持任何兼容 LiteLLM 接口格式的大语言模型 (LLM)，例如 DeepSeek、OpenAI、Anthropic Claude、本地的 Ollama 等，使得你可以任意切换底层模型而不需要修改代码。

如果你想要更改默认的 `deepseek/deepseek-chat` 模型，请配置项目根目录下的 `.env` 文件。

## 配置基本模型

你可以在 `.env` 内修改相关的配置来切换模型及其鉴权：

```env
# 你的 API Key
AI_API_KEY=your_api_key_here

# 指定想要使用的模型标识符 (参考 LiteLLM 的命名规范)
AI_MODEL=gpt-4o

# (可选) 当遇到大模型频率限制或者异常时，自动退后轮询的后备模型列表 (逗号分隔)
AI_FALLBACK_MODELS=gpt-4-turbo,claude-3-opus-20240229
```

配置后，CodeMind 会自动加载相关的环境变量并通过 `LiteLLM` 进行接口调用。


## OpenAI
如果你想切换到 OpenAI 的模型 (比如 `gpt-4o`):

```env
AI_MODEL=gpt-4o
AI_API_KEY=sk-xxxxxx
# 如果使用了代理镜像站，则请取消注释下方并修改：
# AI_BASE_URL=https://api.openai-proxy.com/v1
```

## Azure OpenAI
如果你的公司或者团队使用的是 Azure OpenAI：

```env
AI_MODEL=azure/my-gpt-4o-deployment
AI_API_KEY=your_azure_api_key
AI_BASE_URL=https://<your_resource_name>.openai.azure.com/
```
> **注意**: `AI_MODEL` 中的名称务必按照 `azure/<your_deployment_id>` 设置，LiteLLM 才能正确识别请求路由。

## 本地大模型 (Ollama)
如果你想在本地通过 Ollama 来运行代码审查 (比如基于 `qwen2.5-coder`)，请保证本地已经启动了服务并在 `.env` 中如此做：

```env
AI_MODEL=ollama/qwen2.5-coder
AI_BASE_URL=http://localhost:11434
# 当使用本地 Ollama 时由于并非所有的接口校验需要该值，可以为空或填充占位符
AI_API_KEY=null
```

> 提示：Ollama 的默认 Token 长度为 `2048`，做 PR Review 可能无法涵盖所有的改动代码长度，建议按照官方指引调整 `OLLAMA_CONTEXT_LENGTH`。

## 更多模型支持
任何 LiteLLM (https://docs.litellm.ai/docs/providers) 支持的模型都可以被直接在此使用，只需保证 `AI_MODEL` 的前缀正确，比如 `anthropic/claude-3-5-sonnet-20240620`、`gemini/gemini-1.5-pro` 等。