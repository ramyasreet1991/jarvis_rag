import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Nifty200 Momentum 30 | Agentic Trading',
  description: 'Multi-agent stock analysis with Red Team governance screening',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
