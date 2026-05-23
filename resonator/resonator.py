from __future__ import annotations

import os
import uuid

from collections.abc import Generator
from threading import Event
from typing import Any

from resonate import Resonate, Context

from resonator import parser


grp = os.getenv("GRP")
pid = os.getenv("PID")
resonate_kwargs = {}
if grp:
    resonate_kwargs["group"] = grp
if pid:
    resonate_kwargs["pid"] = pid
resonate = Resonate.remote(**resonate_kwargs)

@resonate.register(name="+")
def add(ctx: Context, x: int, y: int) -> int:
    print(f"{grp}: {x} + {y}")
    return x + y

@resonate.register(name="-")
def sub(ctx: Context, x: int, y: int) -> int:
    print(f"{grp}: {x} - {y}")
    return x - y

@resonate.register(name="*")
def mul(ctx: Context, x: int, y: int) -> int:
    print(f"{grp}: {x} * {y}")
    return x * y

@resonate.register(name="=")
def clc(ctx: Context, expr: parser.Expr) -> Generator[Any, Any, int]:
    if grp:
        print(f"{grp}/{pid}: {expr}")

    match expr:
        case (op, lhs, rhs):
            # Send the expressions to the exp task queue with
            # preference.
            #
            # The expressions are sent to the task queue as invocations
            # which return a handle so we can wait for the result later.
            px = yield ctx.rfi(clc, lhs).options(target="poll://exp/lhs")
            py = yield ctx.rfi(clc, rhs).options(target="poll://exp/rhs")

            # Wait for results from the lhs and rhs tasks.
            vx = yield px
            vy = yield py

            # Send the operation to the ops task queue.
            #
            # The operation is sent to the task queue as a call which returns
            # the result directly.
            return (yield ctx.rfc(op, vx, vy).options(target="poll://ops"))

        case x:
            return x

def run():
    resonate.start()

    # Worker loop: wait for tasks until interrupted.
    if grp:
        print(f"worker started: group={grp} pid={pid}", flush=True)
        try:
            Event().wait()
        except KeyboardInterrupt:
            resonate.stop()
        return

    print("""\
RRRR   EEEEE  SSSSS   OOO   N   N  AAAAA  TTTTT  OOO   RRRR
R   R  E      S      O   O  NN  N  A   A    T   O   O  R   R
RRRR   EEEE   SSSSS  O   O  N N N  AAAAA    T   O   O  RRRR
R  R   E          S  O   O  N  NN  A   A    T   O   O  R  R
R   R  EEEEE  SSSSS   OOO   N   N  A   A    T    OOO   R   R

Resonator is a distributed calculator that can calculate basic
arithmetic expressions that contain numbers and the following
symbols:
    ( ) + - *

Resonator splits an expression into tasks (sub expressions) and
distributes those tasks to workers to calculate.

Give it a try by typing an expression such as:
    (1 + 2)
    (1 + 2) * 3
    (1 + 2) * (3 - 4)
""")

    while True:
        try:
            if expr := input("❯ "):
                # `clc.run(...)` blocks until the workflow completes and
                # returns the result directly.
                result = clc.run(str(uuid.uuid4()), parser.parse(expr))
                print(f"\n{expr}\n= {result}\n")
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Something went wrong: {e}")

    resonate.stop()


if __name__ == "__main__":
    run()
