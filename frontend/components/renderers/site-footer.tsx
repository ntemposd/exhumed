export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={className ? `siteFooter ${className}`.trim() : "siteFooter"}>
      <span className="siteFooterCredits">
        Built with ❤️ by <a className="siteFooterLink" href="https://ntemposd.me" target="_blank" rel="noreferrer">ntemposd</a>
      </span>
      <span className="siteFooterSep" aria-hidden="true" />
      <span className="siteFooterStarLine">
        <a className="siteFooterPartialLink" href="https://github.com/ntemposd/exhumed" target="_blank" rel="noreferrer">⭐ Star on <span className="siteFooterPartialLinkUnderline">GitHub</span></a>
      </span>
    </footer>
  );
}
