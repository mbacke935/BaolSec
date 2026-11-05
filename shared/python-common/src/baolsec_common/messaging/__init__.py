"""Messagerie BaolSec : interface (I-9) et règle des 5 tentatives puis dlq.

L'adaptateur concret s'importe explicitement :
    from baolsec_common.messaging.nats_adapter import NatsBroker
"""
from .interfaces import Broker, BrokerUnavailable, PublishResult, Publisher, ReceivedMessage, Subscription
from .retry import ProcessingError, RetryPolicy, build_dlq_message, process

__all__ = [
    "Broker",
    "BrokerUnavailable",
    "ProcessingError",
    "PublishResult",
    "Publisher",
    "ReceivedMessage",
    "RetryPolicy",
    "Subscription",
    "build_dlq_message",
    "process",
]
