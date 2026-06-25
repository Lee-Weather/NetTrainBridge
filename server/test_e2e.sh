#!/bin/bash
# GradMotion Server 全链路验证脚本
# 使用方法: bash test_e2e.sh [BASE_URL]

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        echo "  ✅ $desc"
        ((PASS++))
    else
        echo "  ❌ $desc (expected: $expected, got: $actual)"
        ((FAIL++))
    fi
}

echo "=== GradMotion Server 全链路验证 ==="
echo "目标: $BASE_URL"
echo ""

# 1. 健康检查
echo "--- 1. 健康检查 ---"
R=$(curl -s "$BASE_URL/health")
check "health" "ok" "$R"
echo ""

# 2. 创建任务
echo "--- 2. 创建任务 ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/test/e2e", "commit_sha": "deadbeef"}')
JOB_ID=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
check "创建任务返回 id" "." "$JOB_ID"
check "初始状态 PENDING" "PENDING" "$R"
echo "  任务 ID: $JOB_ID"
echo ""

# 3. 查询待处理任务
echo "--- 3. 查询待处理任务 ---"
R=$(curl -s "$BASE_URL/jobs/pending")
check "pending 列表包含任务" "$JOB_ID" "$R"
echo ""

# 4. 查询单个任务
echo "--- 4. 查询单个任务 ---"
R=$(curl -s "$BASE_URL/jobs/$JOB_ID")
check "查询单个任务" "$JOB_ID" "$R"
echo ""

# 5. Agent 抢占任务
echo "--- 5. Agent 抢占任务 ---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/claim" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test-agent"}')
check "抢占成功状态 ASSIGNED" "ASSIGNED" "$R"
check "agent_id 已设置" "test-agent" "$R"
echo ""

# 6. 重复抢占应失败
echo "--- 6. 重复抢占应失败 ---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/claim" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "another-agent"}')
check "重复抢占返回 409" "409" "$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$BASE_URL/jobs/$JOB_ID/claim" -H "Content-Type: application/json" -d '{"agent_id": "another-agent"}')"
echo ""

# 7. 更新状态为 RUNNING
echo "--- 7. 更新状态为 RUNNING ---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "RUNNING"}')
check "状态变为 RUNNING" "RUNNING" "$R"
echo ""

# 8. 上报日志
echo "--- 8. 上报日志 ---"
R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
  -H "Content-Type: application/json" \
  -d '{"content": "Epoch 1, Loss: 0.5"}')
check "日志上报 ok" "ok" "$R"

R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
  -H "Content-Type: application/json" \
  -d '{"content": "Epoch 2, Loss: 0.3"}')
check "日志上报 ok (2)" "ok" "$R"
echo ""

# 9. 查询日志
echo "--- 9. 查询日志 ---"
R=$(curl -s "$BASE_URL/jobs/$JOB_ID/logs")
check "日志包含 Epoch 1" "Epoch 1" "$R"
check "日志包含 Epoch 2" "Epoch 2" "$R"

R=$(curl -s "$BASE_URL/jobs/$JOB_ID/logs?tail=1")
check "tail=1 仅返回 1 条" "Epoch 2" "$R"
echo ""

# 10. 上报指标
echo "--- 10. 上报指标 ---"
R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/metrics" \
  -H "Content-Type: application/json" \
  -d '{"metrics": [{"step": 100, "loss": 0.5, "reward": 1.2, "lr": 0.001}, {"step": 200, "loss": 0.3, "reward": 1.5, "lr": 0.0005}]}')
check "指标上报 count=2" "2" "$R"
echo ""

# 11. 查询指标
echo "--- 11. 查询指标 ---"
R=$(curl -s "$BASE_URL/jobs/$JOB_ID/metrics")
check "指标包含 step 100" "100" "$R"
check "指标包含 step 200" "200" "$R"

R=$(curl -s "$BASE_URL/jobs/$JOB_ID/metrics?since_step=100")
check "since_step=100 返回 step>100" "200" "$R"
echo ""

# 11b. 上报心跳
echo "--- 11b. 上报心跳 ---"
R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test-agent", "gpu_util": 85.0, "gpu_mem_used": 20.0, "gpu_mem_total": 24.0}')
check "心跳上报 ok" "ok" "$R"

R=$(curl -s "$BASE_URL/jobs/$JOB_ID/heartbeat")
check "查询最新心跳 gpu_util=85" "85" "$R"
check "查询最新心跳 agent_id" "test-agent" "$R"
echo ""

# 12. 上传模型
echo "--- 12. 上传模型 ---"
echo "e2e test checkpoint content" > /tmp/e2e_model.pt
R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/checkpoint?chunk_index=0&total_chunks=1" \
  -F "file=@/tmp/e2e_model.pt")
check "上传完成 status=completed" "completed" "$R"
echo ""

# 13. 下载模型
echo "--- 13. 下载模型 ---"
curl -s -o /tmp/e2e_downloaded.pt "$BASE_URL/jobs/$JOB_ID/checkpoint/e2e_model.pt"
ORIG_MD5=$(md5sum /tmp/e2e_model.pt | awk '{print $1}')
DOWN_MD5=$(md5sum /tmp/e2e_downloaded.pt | awk '{print $1}')
if [ "$ORIG_MD5" = "$DOWN_MD5" ]; then
    echo "  ✅ 下载文件 md5 一致: $ORIG_MD5"
    ((PASS++))
else
    echo "  ❌ md5 不一致: orig=$ORIG_MD5 down=$DOWN_MD5"
    ((FAIL++))
fi
echo ""

# 14. 更新状态为 COMPLETED
echo "--- 14. 更新状态为 COMPLETED ---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/status" \
  -H "Content-Type: application/json" \
  -d '{"status": "COMPLETED"}')
check "状态变为 COMPLETED" "COMPLETED" "$R"
check "end_time 已填充" "end_time" "$R"
echo ""

# 15. GitHub Webhook
echo "--- 15. GitHub Webhook ---"
R=$(curl -s -X POST "$BASE_URL/webhook/github" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d '{"repository": {"clone_url": "https://github.com/test/webhook"}, "after": "cafe1234", "ref": "refs/heads/main"}')
check "Webhook accepted" "accepted" "$R"
echo ""

# 清理
rm -f /tmp/e2e_model.pt /tmp/e2e_downloaded.pt

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ $FAIL -eq 0 ]; then
    echo "全链路验证通过！"
else
    echo "存在失败项，请检查！"
fi
