import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import "leaflet/dist/leaflet.css";
import Header from "./components/Header";
import Footer from "./components/Footer";
import SWRProvider from "./components/SWRProvider";
import { LanguageProvider } from "./lib/i18n/LanguageContext";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

const poppins = Poppins({
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

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
    <html lang="en" className="scroll-smooth">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className={`${inter.variable} ${poppins.variable} antialiased selection:bg-accent/30 selection:text-primary-900`}>
        <a
          href="#main-content"
          className="visually-hidden focus:!clip-auto focus:!w-auto focus:!h-auto focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:bg-accent focus:text-primary-800 focus:px-4 focus:py-2 focus:rounded-lg focus:font-semibold"
        >
          Skip to main content
        </a>
        <LanguageProvider>
          <SWRProvider>
            <Header />
            {children}
            <Footer />
          </SWRProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
