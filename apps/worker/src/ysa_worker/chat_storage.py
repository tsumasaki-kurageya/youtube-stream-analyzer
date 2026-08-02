from __future__ import annotations

from collections.abc import Iterable

import psycopg

from ysa_worker.chat_replay import ChatMessage


class ChatMessageRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def save_batch(
        self,
        stream_id: str,
        collection_job_id: str,
        messages: Iterable[ChatMessage],
    ) -> int:
        rows = [
            (
                stream_id,
                collection_job_id,
                message.external_id,
                message.author_external_id,
                message.author_name,
                message.text,
                message.published_at,
                message.elapsed_milliseconds,
            )
            for message in messages
        ]
        if not rows:
            return 0

        inserted = 0
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for row in rows:
                    cursor.execute(
                        """
                        INSERT INTO chat.chat_messages(
                            stream_id, collection_job_id, external_message_id,
                            author_external_id, author_name, message_text,
                            published_at, elapsed_milliseconds
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (stream_id, external_message_id) DO NOTHING
                        RETURNING id
                        """,
                        row,
                    )
                    if cursor.fetchone() is not None:
                        inserted += 1
        return inserted
