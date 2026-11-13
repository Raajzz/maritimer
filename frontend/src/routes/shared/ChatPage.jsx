import { MessageSquare } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ChatPanel } from "../../components/domain";
import { Badge, Card, EmptyState, Loader, PageHeader } from "../../components/ui";
import { useResource } from "../../hooks/useResource";
import { relativeTime } from "../../lib/format";

export default function ChatPage() {
  const { id } = useParams();
  const threads = useResource("/chat/threads?page_size=100", { pollMs: 15000 });
  return (
    <div className="stack">
      <PageHeader title="Messages" sub="Owner ↔ agent per port call, agent ↔ merchant per service request." />
      <div className={`grid ${id ? "grid-main-side" : ""}`}>
        {id && <Card><ChatPanel key={id} threadId={id} /></Card>}
        <Card title="Conversations">
          <Loader resource={threads}>
            {(page) => page.results.length ? (
              <div className="stack-sm">
                {page.results.map((t) => (
                  <Link key={t.id} to={`/chat/${t.id}`} className="card card-link" style={{ padding: 12, borderColor: String(t.id) === id ? "var(--color-accent)" : undefined }}>
                    <div className="row-between">
                      <span className="small strong truncate" style={{ maxWidth: "75%" }}>{t.subject}</span>
                      {t.unread_count > 0 && <Badge tone="cta">{t.unread_count} new</Badge>}
                    </div>
                    <div className="xs muted truncate">{t.last_message ? `${t.last_message.sender_organization.legal_name}: ${t.last_message.body}` : "No messages yet"}</div>
                    <div className="xs muted">{t.port_call.reference}{t.last_message_at ? ` · ${relativeTime(t.last_message_at)}` : ""}{t.is_closed ? " · closed" : ""}</div>
                  </Link>
                ))}
              </div>
            ) : <EmptyState icon={MessageSquare} title="No conversations yet">Threads open automatically when a request is accepted.</EmptyState>}
          </Loader>
        </Card>
      </div>
    </div>
  );
}
