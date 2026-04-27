import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  icons: {
    icon: '/FoodcastIcon.svg'
  },
  title: "FOODCAST — AI Food Price Forecasting",
  description:
    "AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets using Machine Learning Algorithms. Check future prices of farm and fish products.",
  keywords:
    "food price forecast, NCR markets, AI forecasting, agri-fishery, Philippines, price prediction, agriculture",
  robots: "index, follow",
  openGraph: {
    title: "FOODCAST — AI Food Price Forecasting",
    description:
      "AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets.",
    type: "website",
    locale: "en_PH",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Poppins:wght@300;400;500;600;700;800;900&display=swap"
          rel="stylesheet"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="antialiased selection:bg-accent/30 selection:text-primary-900">
        <a
          href="#main-content"
          className="visually-hidden focus:!clip-auto focus:!w-auto focus:!h-auto focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:bg-accent focus:text-primary-800 focus:px-4 focus:py-2 focus:rounded-lg focus:font-semibold"
        >
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
