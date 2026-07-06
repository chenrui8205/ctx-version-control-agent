"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useRouter } from "next/navigation";

/** Renders a compiled wiki page; strips frontmatter, rewrites relative links to /wiki/. */
export default function PageView({ content }: { content: string }) {
  const router = useRouter();
  const body = content.replace(/^---[\s\S]*?---\n/, "");
  return (
    <div className="md">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const external = href?.startsWith("http");
            return (
              <a
                href={external ? href : `/wiki/${href}`}
                target={external ? "_blank" : undefined}
                onClick={(e) => {
                  if (!external && href) {
                    e.preventDefault();
                    router.push(`/wiki/${href}`);
                  }
                }}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {body}
      </Markdown>
    </div>
  );
}
