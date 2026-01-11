# Sora API 接口参考文档

> 本文档整理了 sora2api 项目中调用的所有 Sora 相关接口

---

## 接口汇总表

### Sora Backend 接口 (Base URL: `https://sora.chatgpt.com/backend`)

| 分类 | Method | Endpoint | 功能 | 鉴权 | Sentinel |
|-----|--------|----------|------|------|----------|
| **用户信息** | GET | `/me` | 获取用户基本信息 | AT | - |
| | GET | `/billing/subscriptions` | 获取订阅信息 | AT | - |
| **Sora2 功能** | GET | `/project_y/invite/mine` | 获取邀请码 | AT | - |
| | GET | `/m/bootstrap` | 激活 Sora2 | AT | - |
| | POST | `/project_y/invite/accept` | 接受邀请码 | AT | - |
| | GET | `/nf/check` | 获取剩余生成次数 | AT | - |
| **用户名** | POST | `/project_y/profile/username/check` | 检查用户名可用性 | AT | - |
| | POST | `/project_y/profile/username/set` | 设置用户名 | AT | - |
| **图片生成** | POST | `/uploads` | 上传图片 | AT | - |
| | POST | `/video_gen` | 生成图片 (t2i/i2i) | AT | ✓ |
| | GET | `/v2/recent_tasks?limit={n}` | 获取图片任务列表 | AT | - |
| **视频生成** | POST | `/nf/create` | 生成视频 (t2v/i2v/remix) | AT | ✓ |
| | POST | `/nf/create/storyboard` | 分镜模式生成视频 | AT | ✓ |
| | GET | `/nf/pending/v2` | 获取待处理任务(轮询) | AT | - |
| | GET | `/project_y/profile/drafts?limit={n}` | 获取视频草稿列表 | AT | - |
| **角色系统** | POST | `/characters/upload` | 上传角色视频 | AT | - |
| | GET | `/project_y/cameos/in_progress/{id}` | 获取角色处理状态 | AT | - |
| | POST | `/project_y/file/upload` | 上传角色头像 | AT | - |
| | POST | `/characters/finalize` | 完成角色创建 | AT | - |
| | POST | `/project_y/cameos/by_id/{id}/update_v2` | 设置角色公开 | AT | - |
| | DELETE | `/project_y/characters/{id}` | 删除角色 | AT | - |
| **发布分享** | POST | `/project_y/post` | 发布视频(获取无水印) | AT | ✓ |
| | DELETE | `/project_y/post/{id}` | 删除发布的帖子 | AT | - |

### Token 刷新接口 (非 Sora Backend)

| Method | URL | 功能 | 鉴权方式 |
|--------|-----|------|---------|
| GET | `https://sora.chatgpt.com/api/auth/session` | ST → AT | Cookie: `__Secure-next-auth.session-token` |
| POST | `https://auth.openai.com/oauth/token` | RT → AT | Body: `refresh_token` + `client_id` |

> **说明:**
> - **AT**: Access Token (Bearer Token 方式)
> - **Sentinel**: 需要 `openai-sentinel-token` Header (随机字符串)
> - **t2i/i2i**: text-to-image / image-to-image
> - **t2v/i2v**: text-to-video / image-to-video

---

## 鉴权方式

**所有接口统一使用 Access Token (AT) 进行鉴权**

```
Authorization: Bearer {access_token}
```

| Token 类型 | 说明 | 用途 |
|-----------|------|-----|
| **AT (Access Token)** | JWT 格式，有效期约 1 小时 | 直接用于 API 鉴权 |
| **ST (Session Token)** | Cookie 格式 | 用于刷新 AT |
| **RT (Refresh Token)** | 长期有效 | 用于刷新 AT |

---

## API Base URL

```
https://sora.chatgpt.com/backend
```

---

## 接口分类

### 1. 用户信息类

#### 1.1 获取用户信息

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/me` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取当前用户基本信息（email, username, name 等） |

**响应示例:**
```json
{
  "email": "user@example.com",
  "username": "user123",
  "name": "John Doe"
}
```

---

#### 1.2 获取订阅信息

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/billing/subscriptions` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取用户的 ChatGPT 订阅状态（Plus/Pro/Team） |

**响应示例:**
```json
{
  "data": [{
    "plan": {
      "id": "chatgpt_plus",
      "title": "ChatGPT Plus"
    },
    "end_ts": "2025-11-13T16:58:21Z"
  }]
}
```

---

### 2. Sora2 功能类

#### 2.1 获取 Sora2 邀请码

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/project_y/invite/mine` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取用户的 Sora2 邀请码及使用情况 |

**响应示例:**
```json
{
  "invite_code": "ABC123",
  "redeemed_count": 2,
  "total_count": 5
}
```

---

#### 2.2 激活 Sora2 (Bootstrap)

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/m/bootstrap` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 激活账号的 Sora2 功能（首次使用时） |

---

#### 2.3 接受 Sora2 邀请码

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/invite/accept` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 使用邀请码激活 Sora2 功能 |

**请求体:**
```json
{
  "invite_code": "ABC123"
}
```

**额外 Header:**
```
Cookie: oai-did={device_id}
```

---

#### 2.4 获取 Sora2 剩余次数

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/nf/check` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取用户 Sora2 剩余的视频生成次数 |

**响应示例:**
```json
{
  "rate_limit_and_credit_balance": {
    "estimated_num_videos_remaining": 27,
    "rate_limit_reached": false,
    "access_resets_in_seconds": 46833
  }
}
```

---

### 3. 用户名管理类

#### 3.1 检查用户名是否可用

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/profile/username/check` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 检查指定用户名是否已被占用 |

**请求体:**
```json
{
  "username": "desired_username"
}
```

**响应示例:**
```json
{
  "available": true
}
```

---

#### 3.2 设置用户名

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/profile/username/set` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 为账号设置用户名（首次设置） |

**请求体:**
```json
{
  "username": "new_username"
}
```

---

### 4. 图片生成类

#### 4.1 上传图片

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/uploads` |
| **鉴权** | AT (Bearer Token) |
| **Content-Type** | `multipart/form-data` |
| **用途** | 上传图片用于 image-to-image 或 image-to-video 生成 |

**表单字段:**
- `file`: 图片文件 (image/png, image/jpeg, image/webp)
- `file_name`: 文件名

**响应示例:**
```json
{
  "id": "upload_xxxxx"
}
```

---

#### 4.2 生成图片

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/video_gen` |
| **鉴权** | AT (Bearer Token) |
| **额外 Header** | `openai-sentinel-token: {random_string}` |
| **用途** | 生成图片（text-to-image 或 image-to-image） |

**请求体:**
```json
{
  "type": "image_gen",
  "operation": "simple_compose",  // 或 "remix" (有输入图片时)
  "prompt": "A beautiful sunset",
  "width": 360,
  "height": 360,
  "n_variants": 1,
  "n_frames": 1,
  "inpaint_items": []  // 若有输入图片: [{"type":"image","frame_index":0,"upload_media_id":"xxx"}]
}
```

**响应示例:**
```json
{
  "id": "task_xxxxx"
}
```

---

#### 4.3 获取图片任务列表

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/v2/recent_tasks?limit={limit}` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取最近的图片生成任务列表（用于轮询结果） |

---

### 5. 视频生成类

#### 5.1 生成视频

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/nf/create` |
| **鉴权** | AT (Bearer Token) |
| **额外 Header** | `openai-sentinel-token: {random_string}` |
| **用途** | 生成视频（text-to-video 或 image-to-video） |

**请求体:**
```json
{
  "kind": "video",
  "prompt": "A cat dancing",
  "orientation": "landscape",  // 或 "portrait"
  "size": "small",             // 或 "large" (Pro HD)
  "n_frames": 450,             // 300=10s, 450=15s, 750=25s
  "model": "sy_8",             // 或 "sy_ore" (Pro 模型)
  "inpaint_items": [],         // 若有输入图片: [{"kind":"upload","upload_id":"xxx"}]
  "style_id": null             // 可选风格 ID
}
```

**响应示例:**
```json
{
  "id": "gen_xxxxx"
}
```

---

#### 5.2 Remix 视频

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/nf/create` |
| **鉴权** | AT (Bearer Token) |
| **额外 Header** | `openai-sentinel-token: {random_string}` |
| **用途** | 基于已有视频进行 remix 创作 |

**请求体:**
```json
{
  "kind": "video",
  "prompt": "Make it more dramatic",
  "inpaint_items": [],
  "remix_target_id": "s_690d100857248191b679e6de12db840e",
  "cameo_ids": [],
  "cameo_replacements": {},
  "model": "sy_8",
  "orientation": "portrait",
  "n_frames": 450,
  "style_id": null
}
```

---

#### 5.3 分镜模式生成视频

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/nf/create/storyboard` |
| **鉴权** | AT (Bearer Token) |
| **额外 Header** | `openai-sentinel-token: {random_string}` |
| **用途** | 使用分镜模式生成多场景视频 |

**请求体:**
```json
{
  "kind": "video",
  "prompt": "Shot 1:\nduration: 5.0sec\nScene: Cat jumping",
  "title": "Draft your video",
  "orientation": "landscape",
  "size": "small",
  "n_frames": 450,
  "storyboard_id": null,
  "inpaint_items": [],
  "remix_target_id": null,
  "model": "sy_8",
  "metadata": null,
  "style_id": null,
  "cameo_ids": null,
  "cameo_replacements": null,
  "audio_caption": null,
  "audio_transcript": null,
  "video_caption": null
}
```

---

#### 5.4 获取待处理任务

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/nf/pending/v2` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取当前用户待处理的视频生成任务（用于轮询进度） |

---

#### 5.5 获取视频草稿列表

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/project_y/profile/drafts?limit={limit}` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 获取最近的视频草稿列表 |

---

### 6. 角色 (Character/Cameo) 类

#### 6.1 上传角色视频

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/characters/upload` |
| **鉴权** | AT (Bearer Token) |
| **Content-Type** | `multipart/form-data` |
| **用途** | 上传视频以创建角色 |

**表单字段:**
- `file`: 视频文件 (video/mp4)
- `timestamps`: 时间戳范围 (如 "0,3")

**响应示例:**
```json
{
  "id": "cameo_xxxxx"
}
```

---

#### 6.2 获取角色处理状态

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **Endpoint** | `/project_y/cameos/in_progress/{cameo_id}` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 查询角色创建的处理进度 |

**响应字段:**
- `status`: 处理状态
- `display_name_hint`: 建议的显示名
- `username_hint`: 建议的用户名
- `profile_asset_url`: 角色头像 URL
- `instruction_set_hint`: 角色指令集

---

#### 6.3 上传角色头像

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/file/upload` |
| **鉴权** | AT (Bearer Token) |
| **Content-Type** | `multipart/form-data` |
| **用途** | 上传角色头像图片 |

**表单字段:**
- `file`: 图片文件 (image/webp)
- `use_case`: "profile"

**响应示例:**
```json
{
  "asset_pointer": "file-xxxxx"
}
```

---

#### 6.4 完成角色创建

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/characters/finalize` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 完成角色创建流程 |

**请求体:**
```json
{
  "cameo_id": "cameo_xxxxx",
  "username": "character_name",
  "display_name": "Character Display Name",
  "profile_asset_pointer": "file-xxxxx",
  "instruction_set": null,
  "safety_instruction_set": null
}
```

**响应示例:**
```json
{
  "character": {
    "character_id": "char_xxxxx"
  }
}
```

---

#### 6.5 设置角色为公开

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/cameos/by_id/{cameo_id}/update_v2` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 将角色设置为公开可见 |

**请求体:**
```json
{
  "visibility": "public"
}
```

---

#### 6.6 删除角色

| 属性 | 值 |
|-----|-----|
| **Method** | `DELETE` |
| **Endpoint** | `/project_y/characters/{character_id}` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 删除已创建的角色 |

---

### 7. 发布/分享类

#### 7.1 发布视频

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **Endpoint** | `/project_y/post` |
| **鉴权** | AT (Bearer Token) |
| **额外 Header** | `openai-sentinel-token: {random_string}` |
| **用途** | 发布视频以获取分享链接（用于获取无水印版本） |

**请求体:**
```json
{
  "attachments_to_create": [{
    "generation_id": "gen_xxxxx",
    "kind": "sora"
  }],
  "post_text": ""
}
```

**响应示例:**
```json
{
  "post": {
    "id": "s_690ce161c2488191a3476e9969911522"
  }
}
```

---

#### 7.2 删除发布的帖子

| 属性 | 值 |
|-----|-----|
| **Method** | `DELETE` |
| **Endpoint** | `/project_y/post/{post_id}` |
| **鉴权** | AT (Bearer Token) |
| **用途** | 删除已发布的帖子 |

---

## Token 刷新接口 (非 Sora Backend)

### ST 转 AT

| 属性 | 值 |
|-----|-----|
| **Method** | `GET` |
| **URL** | `https://sora.chatgpt.com/api/auth/session` |
| **鉴权** | Cookie: `__Secure-next-auth.session-token={session_token}` |
| **用途** | 使用 Session Token 获取新的 Access Token |

**响应示例:**
```json
{
  "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI...",
  "user": {
    "email": "user@example.com"
  },
  "expires": "2025-01-15T12:00:00.000Z"
}
```

---

### RT 转 AT

| 属性 | 值 |
|-----|-----|
| **Method** | `POST` |
| **URL** | `https://auth.openai.com/oauth/token` |
| **鉴权** | 无（通过请求体传递 RT） |
| **用途** | 使用 Refresh Token 获取新的 Access Token |

**请求体:**
```json
{
  "client_id": "app_LlGpXReQgckcGGUo2JrYvtJK",
  "grant_type": "refresh_token",
  "redirect_uri": "com.openai.chat://auth0.openai.com/ios/com.openai.chat/callback",
  "refresh_token": "{refresh_token}"
}
```

**响应示例:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI...",
  "refresh_token": "new_refresh_token",
  "expires_in": 3600
}
```

---

## 特殊 Header 说明

### openai-sentinel-token

用于生成类请求的安全校验，值为随机字符串（10-20 个字母数字字符）。

**需要添加此 Header 的接口:**
- `POST /video_gen` (图片生成)
- `POST /nf/create` (视频生成)
- `POST /nf/create/storyboard` (分镜生成)
- `POST /project_y/post` (发布视频)

---

## 支持的风格 ID

| Style ID | 名称 |
|----------|-----|
| `festive` | 节日风格 |
| `kakalaka` | Kakalaka 风格 |
| `news` | 新闻风格 |
| `selfie` | 自拍风格 |
| `handheld` | 手持风格 |
| `golden` | 金色风格 |
| `anime` | 动漫风格 |
| `retro` | 复古风格 |
| `nostalgic` | 怀旧风格 |
| `comic` | 漫画风格 |

---

## 模型参数说明

### Video Model

| model 值 | 说明 |
|---------|------|
| `sy_8` | 标准模型 |
| `sy_ore` | Pro 模型（需要 Pro 订阅） |

### Video Size

| size 值 | 说明 |
|--------|------|
| `small` | 标准分辨率 |
| `large` | HD 高清（需要 Pro 订阅） |

### Video Frames

| n_frames 值 | 时长 |
|------------|------|
| `300` | 10 秒 |
| `450` | 15 秒 |
| `750` | 25 秒（需要 Pro 订阅） |

---

## 错误码

| 错误码 | 说明 |
|-------|------|
| `token_invalidated` | Token 已失效，需要重新获取 |
| `token_expired` | Token 已过期 |
| `unsupported_country_code` | 当前地区不支持 Sora |
| `heavy_load` | 服务器负载过高，需要重试 |

---

## 接口调用流程图

### 视频生成流程

```
1. [可选] POST /uploads          # 上传输入图片
        ↓
2. POST /nf/create               # 发起生成请求，返回 task_id
        ↓
3. GET /nf/pending/v2            # 轮询任务状态
        ↓ (重复直到完成)
4. 获取视频 URL
        ↓
5. [可选] POST /project_y/post   # 发布以获取无水印版本
```

### 角色创建流程

```
1. POST /characters/upload       # 上传角色视频，返回 cameo_id
        ↓
2. GET /project_y/cameos/in_progress/{cameo_id}  # 轮询处理状态
        ↓ (重复直到完成)
3. GET {profile_asset_url}       # 下载角色头像
        ↓
4. POST /project_y/file/upload   # 重新上传头像，获取 asset_pointer
        ↓
5. POST /characters/finalize     # 完成角色创建
        ↓
6. [可选] POST /project_y/cameos/by_id/{cameo_id}/update_v2  # 设为公开
```

---

*文档生成时间: 2026-01-10*
