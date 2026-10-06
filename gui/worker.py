"""后台生成 worker（threading + queue，回主线程安全）。

设计：
- 实际图像生成在**单个后台线程**运行；
- worker 内**不触碰任何 Tk widget**，只做纯计算（调用 src 正式后端 API）；
- 结果/异常经 queue.Queue 回传，由主线程通过 root.after 轮询取出并更新 UI；
- 同一时间只允许一个任务（由 App 层控制 busy）；
- 本轮不实现 Cancel。

后端调用统一入口 run_mode()：调用 src.algorithms 的正式四模式，
**不复制任何算法逻辑**，也不通过 subprocess 调 CLI。
"""

import queue
import threading


# 正式模式 -> 后端函数名（延迟 import，避免模块加载期依赖 cv2）
def _get_backend(mode):
    from src import algorithms
    mapping = {
        "classic": algorithms.classic,
        "bayer4": algorithms.bayer4,
        "adaptive_fine": algorithms.adaptive_fine,
        "adaptive_bold": algorithms.adaptive_bold,
    }
    if mode not in mapping:
        raise ValueError(f"未知模式: {mode}")
    return mapping[mode]


def run_mode(mode, params, source_bgr):
    """按模式调用正式后端 API，返回最终结果。

    流程（Color Fill 是统一下游 renderer，不进入四算法内部）：

        run_mode(...) -> binary result（已含 invert 语义）
            if not color_fill:  返回 binary result
            else:               apply_color_fill(source_bgr, binary_result)

    仅做参数透传与下游渲染组合，不含任何算法逻辑副本。
    """
    fn = _get_backend(mode)
    common = dict(
        output_width=params["output_width"],
        pixel_block_size=params["pixel_block_size"],
        invert=params.get("invert", False),
    )
    if mode == "classic":
        binary = fn(source_bgr, t=params["t"], b=params["b"],
                    equalize=params["equalize"], **common)
    elif mode == "bayer4":
        binary = fn(source_bgr, matrix_size=params["matrix_size"],
                    tone_bias=params["tone_bias"], **common)
    elif mode in ("adaptive_fine", "adaptive_bold"):
        binary = fn(source_bgr, block_size=params["block_size"],
                    c=params["c"], **common)
    else:
        raise ValueError(f"未知模式: {mode}")

    if not params.get("color_fill", False):
        return binary

    # 统一下游 renderer：只服从 invert 后的最终 mask，不复制算法逻辑
    from src.render import apply_color_fill
    return apply_color_fill(source_bgr, binary)


class GenerationWorker:
    """单次生成任务封装。

    用法：
        w = GenerationWorker(root, mode, params, source, key)
        w.start()                      # 启动后台线程
        # 主线程用 root.after 轮询 w.poll()
        ok, payload = w.poll()         # 未完成返回 (None, None)
        # ok=True -> payload=result；ok=False -> payload=异常
    """

    def __init__(self, root, mode, params, source_bgr, key):
        self.root = root
        self.mode = mode
        self.params = dict(params)
        self.source_bgr = source_bgr
        self.key = key
        self._q = queue.Queue(maxsize=1)
        self._thread = None
        self._done = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """后台线程体：纯计算，结果/异常入队。"""
        try:
            result = run_mode(self.mode, self.params, self.source_bgr)
            self._q.put((True, result))
        except Exception as exc:  # noqa: BLE001 —— 任何异常都要回传，防止线程静默死亡
            self._q.put((False, exc))

    def poll(self):
        """主线程调用：非阻塞取结果。返回 (ok, payload) 或 (None, None)。"""
        if self._done:
            return None, None
        try:
            ok, payload = self._q.get_nowait()
            self._done = True
            return ok, payload
        except queue.Empty:
            return None, None

    def is_done(self):
        return self._done
