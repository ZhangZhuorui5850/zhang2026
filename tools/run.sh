#!/usr/bin/env bash
# run.sh · 启动 / 观察 / 收尾 三合一（P8 的可执行版本）
# 用法：
#   bash run.sh start   [日志名]     启动训练（tmux 优先，其次 nohup），写 pid
#   bash run.sh watch   [日志名]     盯日志，每 60 秒一行 [MONITOR]
#   bash run.sh status  [日志名]     看一眼进程与最新指标
#   bash run.sh stop    [日志名]     只停本脚本启动的进程
#   bash run.sh tail    [日志名]     最近 40 行
set -u

MODE="${1:-start}"
NAME="${2:-main}"
LOG="runs/50_logs/${NAME}.log"
PIDFILE="runs/50_logs/${NAME}.pid"
ENTRY="${ENTRY:-train_template.py}"
CONFIG="${CONFIG:-config.json}"

mkdir -p runs/50_logs runs/70_ckpt

case "$MODE" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "× 已有实例在跑 (pid=$(cat "$PIDFILE"))，先 stop 或换日志名"; exit 1
    fi
    CMD="python3 $ENTRY --mode train --config $CONFIG"
    echo "[CONFIG] cmd=$CMD log=$LOG" | tee -a "$LOG"
    if command -v tmux >/dev/null 2>&1; then
      tmux kill-session -t mars 2>/dev/null
      tmux new -d -s mars "$CMD 2>&1 | tee -a $LOG"
      tmux list-panes -t mars -F '#{pane_pid}' > "$PIDFILE" 2>/dev/null
      echo "√ 已用 tmux 启动（会话名 mars）。断线重连：tmux attach -t mars"
    else
      nohup bash -c "$CMD >> $LOG 2>&1" &
      echo $! > "$PIDFILE"
      echo "√ 已用 nohup 启动 (pid=$(cat "$PIDFILE"))"
    fi
    sleep 20
    echo "--- 启动自检（必须看到 [CONFIG] 或 [STEP]，否则立即排查）---"
    tail -n 15 "$LOG"
    ;;

  watch)
    python3 monitor.py --log "$LOG" --progress runs/40_progress.md --every 60
    ;;

  status)
    if [ -f "$PIDFILE" ]; then
      PID="$(cat "$PIDFILE")"
      if kill -0 "$PID" 2>/dev/null; then echo "进程存活 pid=$PID"; else echo "进程已退出 pid=$PID"; fi
    else
      echo "无 pid 记录"
    fi
    echo "--- 最新进度 ---"
    grep -E "^\[STEP\]|^\[EVAL\]|^\[DONE\]|^\[FATAL\]" "$LOG" 2>/dev/null | tail -5
    echo "--- 日志体积 ---"
    ls -lh "$LOG" 2>/dev/null
    ;;

  stop)
    if [ -f "$PIDFILE" ]; then
      PID="$(cat "$PIDFILE")"
      # 只杀本脚本记录的进程组，不用 pkill -f 误伤
      kill "$PID" 2>/dev/null
      sleep 2
      kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
      echo "√ 已停止 pid=$PID"
      rm -f "$PIDFILE"
    else
      echo "无 pid 记录，未做任何操作"
    fi
    ;;

  tail)
    tail -n 40 "$LOG"
    ;;

  *)
    echo "未知模式: $MODE（start|watch|status|stop|tail）"; exit 2
    ;;
esac
