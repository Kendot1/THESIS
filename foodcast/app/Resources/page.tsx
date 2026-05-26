"use client";
import { useState, useEffect } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import Image from "next/image";
import ScrollReveal from "../components/ScrollReveal";
import { useLanguage } from "../lib/i18n/LanguageContext";
import {
    Zap,
    Activity,
    Cpu,
    Table,
    Flame,
    Hash,
    HardDrive,
    ExternalLink,
    Bot,
    FastForward,
    Landmark,
    Newspaper,
    FileCode,
    Database,
    Globe,
    Triangle,
    Github,
    Sparkles,
    ArrowRight
} from "lucide-react";

const resourceGroups = [
    {
        title: "Machine Learning & Data Science",
        resources: [
            { name: "LightGBM", description: "Efficient gradient boosting framework for building high-performance prediction models.", icon: Zap, logo: "https://raw.githubusercontent.com/microsoft/LightGBM/master/docs/logo/LightGBM_logo_black_text.svg", link: "https://lightgbm.readthedocs.io/" },
            { name: "LSTM", description: "Long Short-Term Memory network architecture optimized for time-series forecasting.", icon: Activity, logo: "https://cdn.simpleicons.org/pytorch/EE4C2C", link: "https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html" },
            { name: "Scikit-learn", description: "Simple and efficient tools for predictive data analysis and statistical modeling.", icon: Cpu, logo: "https://cdn.simpleicons.org/scikitlearn", link: "https://scikit-learn.org/" },
            { name: "Pandas", description: "Fast, powerful, and flexible open-source data analysis and manipulation tool.", icon: Table, logo: "https://cdn.simpleicons.org/pandas/150458", link: "https://pandas.pydata.org/" },
            { name: "PyTorch", description: "An open-source machine learning framework that accelerates the path from research prototyping to production.", icon: Flame, logo: "https://cdn.simpleicons.org/pytorch/EE4C2C", link: "https://pytorch.org/" },
            { name: "NumPy", description: "The fundamental package for scientific computing with Python and large multi-dimensional arrays.", icon: Hash, logo: "https://cdn.simpleicons.org/numpy/013243", link: "https://numpy.org/" },
            { name: "Joblib", description: "A set of tools to provide lightweight pipelining and disk-caching in Python.", icon: HardDrive, logo: "https://tse4.mm.bing.net/th/id/OIP.9jHkXqDnBXFArRaGU3IApAHaG0?r=0&cb=thfvnextfalcon&rs=1&pid=ImgDetMain&o=7&rm=3", link: "https://joblib.readthedocs.io/" },
            { name: "HTTPX", description: "A fully featured HTTP client for Python 3, which provides async APIs.", icon: ExternalLink, logo: "https://cdn.simpleicons.org/python/3776AB", link: "https://www.python-httpx.org/" },
        ]
    },
    {
        title: "AI Models",
        resources: [
            { name: "Google Gemini", description: "Google's largest and most capable AI models, used for advanced reasoning and insights.", icon: Bot, logo: "https://cdn.simpleicons.org/googlegemini/8E75B2", link: "https://deepmind.google/technologies/gemini/" },
            { name: "Groq AI", description: "Ultra-fast AI inference platform designed for high-performance LLM processing.", icon: FastForward, logo: "https://www.ciscoinvestments.com/assets/logos/groq-logo.png", link: "https://groq.com/" },
        ]
    },
    {
        title: "Institution",
        resources: [
            { name: "Dept. of Agriculture", description: "The principal agency responsible for the promotion of agri-fishery development in the Philippines.", icon: Landmark, logo: "https://imgs.search.brave.com/gRkFFdg5c09KekCzKcOK-28ekER7IWvwEhGQi294Wng/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly9hc3Np/c3RhbmNlLnBoL3dw/LWNvbnRlbnQvdXBs/b2Fkcy8yMDIzLzEy/L0RBLWxvZ28uanBn", link: "https://www.da.gov.ph/" },
            { name: "ABS-CBN News", description: "Leading news and information organization in the Philippines, providing market trends and reports.", icon: Newspaper, logo: "https://data-corporate.abs-cbn.com/wp-content/uploads/2025/05/02130214/abs-cbn-logo-for-newsroom-scaled.jpg", link: "https://news.abs-cbn.com/" },
        ]
    },
    {
        title: "Other Tools",
        resources: [
            { name: "Python", description: "High-level programming language used for data science and backend development.", icon: FileCode, logo: "https://imgs.search.brave.com/slOxOc-tDP66_RuGr9Qf6olFlkr5Po9VT0v8z4SBs98/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly9jZG4u/aWNvbnNjb3V0LmNv/bS9pY29uL2ZyZWUv/cG5nLTI1Ni9mcmVl/LXB5dGhvbi1pY29u/LXN2Zy1kb3dubG9h/ZC1wbmctMjI2MDUx/LnBuZz9mPXdlYnAm/dz0xMjg", link: "https://www.python.org/" },
            { name: "Supabase", description: "Open source Firebase alternative providing database and authentication services.", icon: Database, logo: "https://cdn.simpleicons.org/supabase", link: "https://supabase.com/" },
            { name: "Next.js", description: "The React framework for building performant and SEO-friendly web applications.", icon: Globe, logo: "/next.svg", link: "https://nextjs.org/" },
            { name: "Vercel", description: "Platform for frontend frameworks and static sites, providing seamless deployment.", icon: Triangle, logo: "https://cdn.simpleicons.org/vercel", link: "https://vercel.com/" },
            { name: "GitHub", description: "Web-based version control and collaboration platform for software development.", icon: Github, logo: "https://cdn.simpleicons.org/github", link: "https://github.com/" },
            { name: "Antigravity", description: "AI-powered development assistant used to build and optimize the platform.", icon: Sparkles, logo: "https://imgs.search.brave.com/bDqXljYPb9fCLJrIaFNZCeWdZDCmDE-1Iq9tTt_7G2Q/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly9yYXcu/Z2l0aHVidXNlcmNv/bnRlbnQuY29tL2xv/YmVodWIvbG9iZS1p/Y29ucy9yZWZzL2hl/YWRzL21hc3Rlci9w/YWNrYWdlcy9zdGF0/aWMtcG5nL2xpZ2h0/L2FudGlncmF2aXR5/LWNvbG9yLnBuZw", link: "https://antigravity.ai" },
            { name: "Crawl4AI", description: "Open-source web crawling framework optimized for LLMs and AI applications.", icon: Bot, logo: "https://cdn.discordapp.com/icons/1278297938551902308/71337092ed954ce09bbe55739b3d3199.png?size=256", link: "https://crawl4ai.com/" },
            { name: "Tailwind CSS", description: "A utility-first CSS framework for rapidly building custom user interfaces.", icon: Sparkles, logo: "https://cdn.simpleicons.org/tailwindcss", link: "https://tailwindcss.com/" },
            { name: "TypeScript", description: "A strongly typed programming language that builds on JavaScript, ensuring type safety.", icon: FileCode, logo: "https://cdn.simpleicons.org/typescript", link: "https://www.typescriptlang.org/" },
            { name: "React", description: "A JavaScript library for building interactive and component-driven user interfaces.", icon: FileCode, logo: "https://cdn.simpleicons.org/react", link: "https://react.dev/" },
            { name: "Recharts", description: "A composable and reliable charting library built on React components.", icon: Activity, logo: "https://cdn.simpleicons.org/react/61DAFB", link: "https://recharts.org/" },
            { name: "Lightweight Charts", description: "Financial HTML5 Canvas charting library built for high performance.", icon: Activity, logo: "https://cdn.simpleicons.org/tradingview", link: "https://tradingview.github.io/lightweight-charts/" },
            { name: "SWR", description: "React Hooks for data fetching with fast, lightweight caching and revalidation.", icon: Zap, logo: "https://cdn.simpleicons.org/swr", link: "https://swr.vercel.app/" },
            { name: "Deno", description: "Secure runtime for JavaScript and TypeScript, powering Supabase Edge Functions.", icon: Bot, logo: "https://cdn.simpleicons.org/deno", link: "https://deno.com/" },
            { name: "BeautifulSoup", description: "Python library used for parsing HTML and XML documents in data scraping.", icon: FileCode, logo: "https://cdn.simpleicons.org/python/3776AB", link: "https://www.crummy.com/software/BeautifulSoup/" },
        ]
    }
];

function ResourceCard({ resource }: { resource: any }) {
    const Icon = resource.icon;
    const [imgError, setImgError] = useState(false);
    const { t } = useLanguage();

    return (
        <div className="bg-white rounded-[1.5rem] sm:rounded-[2rem] p-8 sm:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col h-full min-h-[300px] transition-all duration-300 hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
            <div className="flex items-center gap-5 mb-5">
                <div className="relative w-14 h-14 sm:w-16 sm:h-16 bg-gray-50 rounded-2xl flex items-center justify-center shrink-0 overflow-hidden p-3">
                    {resource.logo && !imgError ? (
                        <Image 
                            src={resource.logo} 
                            alt={resource.name} 
                            fill
                            unoptimized
                            className="object-contain p-3"
                            style={{ display: imgError ? 'none' : 'block' }}
                            onError={() => setImgError(true)}
                        />
                    ) : (
                        <div className="flex items-center justify-center w-full h-full animate-fade-in">
                            <Icon className="w-7 h-7 text-orange" />
                        </div>
                    )}
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-[#0B3D2E]" style={{ fontFamily: "var(--font-display)" }}>
                    {resource.name}
                </h3>
            </div>

            <p className="text-gray-500 text-sm sm:text-base leading-relaxed mb-8 flex-grow">
                {resource.description}
            </p>

            <a
                href={resource.link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-[#0B3D2E] text-xs sm:text-sm font-bold uppercase tracking-wider hover:text-orange transition-colors group"
            >
                {t("learnMore")}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </a>
        </div>
    );
}

function SectionHeading({ title }: { title: string }) {
    return (
        <div className="flex items-center gap-4 mb-8 sm:mb-12">
            <div className="h-[2px] w-12 sm:w-16 bg-primary-800/20" />
            <h2 className="text-2xl sm:text-4xl font-bold text-[#0B3D2E]" style={{ fontFamily: "var(--font-display)" }}>
                {title}
            </h2>
        </div>
    );
}

export default function ResourcesPage() {
    const [isLoading, setIsLoading] = useState(true);
    const { t, isTransitioning } = useLanguage();

    useEffect(() => {
        const timer = setTimeout(() => setIsLoading(false), 200);
        return () => clearTimeout(timer);
    }, []);

    if (isLoading || isTransitioning) {
        return (
            <div className="flex flex-col min-h-screen bg-surface">
                <Header />
                <main className="flex-grow">
                    {/* Hero Skeleton */}
                    <section className="relative py-12 sm:py-20 pt-28 sm:pt-36 overflow-hidden bg-primary-900">
                        <div className="relative z-10 max-w-[90rem] mx-auto px-5 lg:px-10">
                            <div className="h-12 sm:h-16 w-3/4 max-w-lg bg-white/10 rounded-2xl mb-4 animate-pulse" />
                            <div className="h-4 sm:h-5 w-full max-w-2xl bg-white/5 rounded-lg mb-2 animate-pulse" />
                            <div className="h-4 sm:h-5 w-5/6 max-w-xl bg-white/5 rounded-lg animate-pulse" />
                        </div>
                    </section>

                    {/* Resources Skeleton */}
                    <section className="py-12 sm:py-20">
                        <div className="max-w-[90rem] mx-auto px-5 lg:px-10 space-y-16 sm:space-y-24">
                            {[1, 2].map((groupIdx) => (
                                <div key={groupIdx}>
                                    {/* Section Heading Skeleton */}
                                    <div className="flex items-center gap-4 mb-8 sm:mb-12">
                                        <div className="h-[2px] w-12 sm:w-16 bg-primary-800/20 animate-pulse" />
                                        <div className="h-8 sm:h-10 w-48 bg-gray-200 rounded-xl animate-pulse" />
                                    </div>
                                    
                                    {/* Cards Grid Skeleton */}
                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
                                        {[1, 2, 3, 4, 5, 6].map((idx) => (
                                            <div key={idx} className="bg-white rounded-[1.5rem] sm:rounded-[2rem] p-6 sm:p-8 border border-gray-50 flex flex-col h-[280px] animate-pulse">
                                                <div className="flex items-center gap-4 mb-4">
                                                    <div className="w-12 h-12 sm:w-14 sm:h-14 bg-gray-100 rounded-2xl shrink-0" />
                                                    <div className="h-6 sm:h-7 w-3/4 bg-gray-200 rounded-lg" />
                                                </div>
                                                
                                                <div className="space-y-2 mt-4 flex-grow">
                                                    <div className="h-3 w-full bg-gray-100 rounded-md" />
                                                    <div className="h-3 w-5/6 bg-gray-100 rounded-md" />
                                                    <div className="h-3 w-4/6 bg-gray-100 rounded-md" />
                                                </div>
                                                
                                                <div className="mt-6 flex items-center gap-2">
                                                    <div className="h-4 w-20 bg-gray-200 rounded-md" />
                                                    <div className="w-4 h-4 bg-gray-100 rounded-full" />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                </main>
                <Footer />
            </div>
        );
    }

    return (
        <div className="flex flex-col min-h-screen bg-surface">
            <Header />
            <main id="main-content" className="flex-grow">
                {/* Hero */}
                <section className="relative py-12 sm:py-20 pt-28 sm:pt-36 overflow-hidden bg-primary-900">
                    <div className="absolute inset-0">
                        <Image
                            src="/Bg-4.jpg"
                            alt="background"
                            fill
                            priority
                            className="object-cover blur-sm scale-105 opacity-60"
                        />
                        <div className="absolute inset-0 bg-primary-900/60" />
                    </div>
                    <div className="relative z-10 max-w-[90rem] mx-auto px-5 lg:px-10">
                        <ScrollReveal animation="fade-up">
                            <h1
                                className="text-3xl sm:text-4xl lg:text-6xl font-bold text-white mb-4"
                                style={{ fontFamily: "var(--font-display)" }}
                            >
                                {t("resources")} <span className="text-white/60">&</span> <br className="sm:hidden" />
                                <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-light to-accent">
                                    {t("references")}
                                </span>
                            </h1>
                            <p className="text-white/60 max-w-2xl text-sm sm:text-lg leading-relaxed">
                                {t("resourcesDesc")}
                            </p>
                        </ScrollReveal>
                    </div>
                </section>

                {/* Groups Content */}
                <section className="py-12 sm:py-20">
                    <div className="max-w-[90rem] mx-auto px-5 lg:px-10 space-y-16 sm:space-y-24">
                        {resourceGroups.map((group, groupIdx) => (
                            <div key={groupIdx}>
                                <ScrollReveal animation="fade-in" delay={100}>
                                    <SectionHeading title={group.title} />
                                </ScrollReveal>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 sm:gap-10">
                                    {group.resources.map((resource, idx) => (
                                        <ScrollReveal key={idx} animation="fade-up" delay={150 + (idx * 50)}>
                                            <ResourceCard resource={resource} />
                                        </ScrollReveal>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </main>
            <Footer />
        </div>
    )
}
