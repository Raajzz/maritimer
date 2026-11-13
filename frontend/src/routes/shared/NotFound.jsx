import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "../../components/ui";

export default function NotFound() {
  return (
    <EmptyState icon={Compass} title="Page not found">
      It may have moved, or you may not have access. <Link to="/">Back to dashboard</Link>
    </EmptyState>
  );
}
