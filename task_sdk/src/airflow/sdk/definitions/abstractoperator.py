#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import datetime
from abc import abstractmethod
from collections.abc import (
    Collection,
    Iterable,
    Mapping,
)
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
)

from airflow.sdk.definitions.node import DAGNode
from airflow.utils.log.secrets_masker import redact
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.weight_rule import WeightRule

# TaskStateChangeCallback = Callable[[Context], None]

if TYPE_CHECKING:
    import jinja2  # Slow import.

    from airflow.models.baseoperatorlink import BaseOperatorLink
    from airflow.sdk.definitions.baseoperator import BaseOperator
    from airflow.sdk.definitions.dag import DAG

    # TODO: Task-SDK
    Context = dict[str, Any]


DEFAULT_OWNER: str = "airflow"
DEFAULT_POOL_SLOTS: int = 1
DEFAULT_PRIORITY_WEIGHT: int = 1
DEFAULT_EXECUTOR: str | None = None
DEFAULT_QUEUE: str = "default"
DEFAULT_IGNORE_FIRST_DEPENDS_ON_PAST: bool = False
DEFAULT_WAIT_FOR_PAST_DEPENDS_BEFORE_SKIPPING: bool = False
DEFAULT_RETRIES: int = 0
DEFAULT_RETRY_DELAY: datetime.timedelta = datetime.timedelta(seconds=300)
MAX_RETRY_DELAY: int = 24 * 60 * 60

# TODO: Task-SDK -- these defaults should be overridable from the Airflow config
DEFAULT_TRIGGER_RULE: TriggerRule = TriggerRule.ALL_SUCCESS
DEFAULT_WEIGHT_RULE: WeightRule = WeightRule.DOWNSTREAM
DEFAULT_TASK_EXECUTION_TIMEOUT: datetime.timedelta | None = None


class NotMapped(Exception):
    """Raise if a task is neither mapped nor has any parent mapped groups."""


class AbstractOperator(DAGNode):
    """
    Common implementation for operators, including unmapped and mapped.

    This base class is more about sharing implementations, not defining a common
    interface. Unfortunately it's difficult to use this as the common base class
    for typing due to BaseOperator carrying too much historical baggage.

    The union type ``from airflow.models.operator import Operator`` is easier
    to use for typing purposes.

    :meta private:
    """

    operator_class: type[BaseOperator] | dict[str, Any]

    priority_weight: int

    # Defines the operator level extra links.
    operator_extra_links: Collection[BaseOperatorLink]

    owner: str
    task_id: str

    outlets: list
    inlets: list
    # TODO:
    trigger_rule: TriggerRule
    _needs_expansion: bool | None = None
    _on_failure_fail_dagrun = False

    HIDE_ATTRS_FROM_UI: ClassVar[frozenset[str]] = frozenset(
        (
            "log",
            "dag",  # We show dag_id, don't need to show this too
            "node_id",  # Duplicates task_id
            "task_group",  # Doesn't have a useful repr, no point showing in UI
            "inherits_from_empty_operator",  # impl detail
            # Decide whether to start task execution from triggerer
            "start_trigger_args",
            "start_from_trigger",
            # For compatibility with TG, for operators these are just the current task, no point showing
            "roots",
            "leaves",
            # These lists are already shown via *_task_ids
            "upstream_list",
            "downstream_list",
            # Not useful, implementation detail, already shown elsewhere
            "global_operator_extra_link_dict",
            "operator_extra_link_dict",
        )
    )

    def get_dag(self) -> DAG | None:
        raise NotImplementedError()

    @property
    def task_type(self) -> str:
        raise NotImplementedError()

    @property
    def operator_name(self) -> str:
        raise NotImplementedError()

    @property
    def inherits_from_empty_operator(self) -> bool:
        raise NotImplementedError()

    @property
    def dag_id(self) -> str:
        """Returns dag id if it has one or an adhoc + owner."""
        dag = self.get_dag()
        if dag:
            return dag.dag_id
        return f"adhoc_{self.owner}"

    @property
    def node_id(self) -> str:
        return self.task_id

    @property
    @abstractmethod
    def task_display_name(self) -> str: ...

    @property
    def label(self) -> str | None:
        if self.task_display_name and self.task_display_name != self.task_id:
            return self.task_display_name
        # Prefix handling if no display is given is cloned from taskmixin for compatibility
        tg = self.task_group
        if tg and tg.node_id and tg.prefix_group_id:
            # "task_group_id.task_id" -> "task_id"
            return self.task_id[len(tg.node_id) + 1 :]
        return self.task_id
