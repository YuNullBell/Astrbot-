# 粤语繁体（astrbot_plugin_cantonese_tc）

让 AstrBot 的机器人只用**香港粤语口语 + 繁體字**回复，人格设定保持不变。

## 原理

两层保险，不单纯依赖模型自觉：

1. **`on_llm_request`**：每次请求模型前，往 `system_prompt` 追加语言要求
   （粵語用詞、全繁體、不加「（粵語）」标注、專有名詞與代碼原樣保留）；
2. **`on_decorating_result`**：发送前用 `zhconv` 把正文里残留的簡體字统一转成繁體
   （默认 `zh-hk` 港式字形），并自动跳过 ```代码块```、`行内代码`、URL、CQ 码。

> 提示词让模型主动说粤语，字形转换兜住「偶尔漏一个简体字」的情况。

## 安装

```bash
cd <AstrBot>/data/plugins
git clone <this-repo> astrbot_plugin_cantonese_tc
pip install zhconv -t <AstrBot>/data/site-packages
```

重启 AstrBot（或热重载插件）后生效。`zhconv` 缺失时插件仍可用，只是没有字形兜底。

## 配置

`data/config/astrbot_plugin_cantonese_tc_config.json`：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 总开关 |
| `scope` | `all` | `all` / `group` / `private` |
| `locale` | `zh-hk` | `zh-hk` 港式 / `zh-tw` 台式 |
| `convert_traditional` | `true` | 是否做简转繁兜底 |
| `protect_code_and_links` | `true` | 转换时保护代码/链接/CQ 码 |
| `style_prompt` | 空 | 留空用内置粤语提示词，可自行改写 |
| `debug` | `false` | 打印注入与转换日志 |

## 命令

```
/繁体测试 这个软件真的很厉害，我们一起去玩吧
```

回复原文与转换结果，用来确认字形兜底是否正常。

## 实测

```
用户：今天好攰啊，今晚食咩好？
回复：攰就咪諗咁多啦，求其煮個麵加隻蛋算數，唔使搞到成個廚神咁喎。
```

转换保护示例：

```
IN : 看这个 ```python print('测试')``` 还有 `a = 这个` 和 https://example.com/这个页面 以及 [CQ:at,qq=123]
OUT: 看這個 ```python print('测试')``` 還有 `a = 这个` 和 https://example.com/这个页面 以及 [CQ:at,qq=123]
```

## 注意

- 只改语言风格，不碰人格 / 记忆 / 工具链；
- `scope` 只区分群聊与私聊，不区分平台；若要只对某个平台生效需自行扩展；
- 依赖 `zhconv`（纯 Python，无编译依赖）。
