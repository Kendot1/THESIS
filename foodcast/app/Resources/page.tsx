"use client";
import { useState } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ScrollReveal from "../components/ScrollReveal";
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
            { name: "LSTM", description: "Long Short-Term Memory network architecture optimized for time-series forecasting.", icon: Activity, logo: null, link: "https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html" },
            { name: "Scikit-learn", description: "Simple and efficient tools for predictive data analysis and statistical modeling.", icon: Cpu, logo: "https://upload.wikimedia.org/wikipedia/commons/0/05/Scikit_learn_logo_small.svg", link: "https://scikit-learn.org/" },
            { name: "Pandas", description: "Fast, powerful, and flexible open-source data analysis and manipulation tool.", icon: Table, logo: "https://upload.wikimedia.org/wikipedia/commons/e/ed/Pandas_logo.svg", link: "https://pandas.pydata.org/" },
            { name: "PyTorch", description: "An open-source machine learning framework that accelerates the path from research prototyping to production.", icon: Flame, logo: "https://raw.githubusercontent.com/pytorch/pytorch/master/docs/source/_static/img/pytorch-logo-dark.png", link: "https://pytorch.org/" },
            { name: "NumPy", description: "The fundamental package for scientific computing with Python and large multi-dimensional arrays.", icon: Hash, logo: "https://upload.wikimedia.org/wikipedia/commons/3/31/NumPy_logo_2020.svg", link: "https://numpy.org/" },
            { name: "Joblib", description: "A set of tools to provide lightweight pipelining and disk-caching in Python.", icon: HardDrive, logo: null, link: "https://joblib.readthedocs.io/" },
            { name: "HTTPX", description: "A fully featured HTTP client for Python 3, which provides async APIs.", icon: ExternalLink, logo: null, link: "https://www.python-httpx.org/" },
        ]
    },
    {
        title: "AI Models",
        resources: [
            { name: "Google Gemini", description: "Google's largest and most capable AI models, used for advanced reasoning and insights.", icon: Bot, logo: "https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d47353047333e6823349.svg", link: "https://deepmind.google/technologies/gemini/" },
            { name: "Groq AI", description: "Ultra-fast AI inference platform designed for high-performance LLM processing.", icon: FastForward, logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/Groq_logo.svg/1200px-Groq_logo.svg.png", link: "https://groq.com/" },
        ]
    },
    {
        title: "Institution",
        resources: [
            { name: "Dept. of Agriculture", description: "The principal agency responsible for the promotion of agri-fishery development in the Philippines.", icon: Landmark, logo: "https://www.da.gov.ph/wp-content/uploads/2018/06/DA-Logo-768x768.png", link: "https://www.da.gov.ph/" },
            { name: "ABS-CBN News", description: "Leading news and information organization in the Philippines, providing market trends and reports.", icon: Newspaper, logo: "https://upload.wikimedia.org/wikipedia/en/thumb/0/0e/ABS-CBN_News_and_Current_Affairs_logo.svg/1200px-ABS-CBN_News_and_Current_Affairs_logo.svg.png", link: "https://news.abs-cbn.com/" },
        ]
    },
    {
        title: "Other Tools",
        resources: [
            { name: "Python", description: "High-level programming language used for data science and backend development.", icon: FileCode, logo: "https://upload.wikimedia.org/wikipedia/commons/c/c3/Python-logo-notext.svg", link: "https://www.python.org/" },
            { name: "Supabase", description: "Open source Firebase alternative providing database and authentication services.", icon: Database, logo: "https://supabase.com/dashboard/img/supabase-logo.svg", link: "https://supabase.com/" },
            { name: "Next.js", description: "The React framework for building performant and SEO-friendly web applications.", icon: Globe, logo: "https://assets.vercel.com/image/upload/v1662130559/nextjs/Icon_light_background.png", link: "https://nextjs.org/" },
            { name: "Vercel", description: "Platform for frontend frameworks and static sites, providing seamless deployment.", icon: Triangle, logo: "https://assets.vercel.com/image/upload/v1588805177/front/favicon/vercel/180x180.png", link: "https://vercel.com/" },
            { name: "GitHub", description: "Web-based version control and collaboration platform for software development.", icon: Github, logo: "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png", link: "https://github.com/" },
            { name: "Antigravity", description: "AI-powered development assistant used to build and optimize the platform.", icon: Sparkles, logo: null, link: "https://antigravity.ai" },
            { name: "Crawl4AI", description: "Open-source web crawling framework optimized for LLMs and AI applications.", icon: Bot, logo: null, link: "https://crawl4ai.com/" },
            { name: "Tailwind CSS", description: "A utility-first CSS framework for rapidly building custom user interfaces.", icon: Sparkles, logo: "https://upload.wikimedia.org/wikipedia/commons/d/d5/Tailwind_CSS_Logo.svg", link: "https://tailwindcss.com/" },
            { name: "TypeScript", description: "A strongly typed programming language that builds on JavaScript, ensuring type safety.", icon: FileCode, logo: "https://upload.wikimedia.org/wikipedia/commons/4/4c/Typescript_logo_2020.svg", link: "https://www.typescriptlang.org/" },
            { name: "Recharts", description: "A composable and reliable charting library built on React components.", icon: Activity, logo: null, link: "https://recharts.org/" },
        ]
    }
];

function ResourceCard({ resource }: { resource: any }) {
    const Icon = resource.icon;
    const [imgError, setImgError] = useState(false);

    return (
        <div className="bg-white rounded-[1.5rem] sm:rounded-[2rem] p-6 sm:p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col h-full transition-all duration-300 hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
            <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 sm:w-14 sm:h-14 bg-gray-50 rounded-2xl flex items-center justify-center shrink-0 overflow-hidden p-2.5">
                    {resource.logo && !imgError ? (
                        <img 
                            src={resource.logo} 
                            alt={resource.name} 
                            className="w-full h-full object-contain"
                            style={{ display: imgError ? 'none' : 'block' }}
                            onError={() => setImgError(true)}
                        />
                    ) : (
                        <div className="flex items-center justify-center w-full h-full animate-fade-in">
                            <Icon className="w-6 h-6 text-orange" />
                        </div>
                    )}
                </div>
                <h3 className="text-base sm:text-xl font-bold text-[#0B3D2E]" style={{ fontFamily: "var(--font-display)" }}>
                    {resource.name}
                </h3>
            </div>

            <p className="text-gray-500 text-xs sm:text-sm leading-relaxed mb-6 flex-grow">
                {resource.description}
            </p>

            <a
                href={resource.link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-[#0B3D2E] text-xs sm:text-sm font-bold uppercase tracking-wider hover:text-orange transition-colors group"
            >
                Learn More
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
    return (
        <div className="flex flex-col min-h-screen bg-surface">
            <Header />
            <main id="main-content" className="flex-grow">
                {/* Hero */}
                <section className="relative py-12 sm:py-20 pt-28 sm:pt-36 overflow-hidden bg-primary-900">
                    <div className="absolute inset-0">
                        <img
                            src="/Bg-4.jpg"
                            alt="background"
                            className="w-full h-full object-cover blur-sm scale-105 opacity-60"
                        />
                        <div className="absolute inset-0 bg-primary-900/60" />
                    </div>
                    <div className="relative z-10 max-w-7xl mx-auto px-5 lg:px-10">
                        <ScrollReveal animation="fade-up">
                            <h1
                                className="text-3xl sm:text-4xl lg:text-6xl font-bold text-white mb-4"
                                style={{ fontFamily: "var(--font-display)" }}
                            >
                                Resources <span className="text-white/60">&</span> <br className="sm:hidden" />
                                <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-light to-accent">
                                    References
                                </span>
                            </h1>
                            <p className="text-white/60 max-w-2xl text-sm sm:text-lg leading-relaxed">
                                Explore the comprehensive ecosystem of technologies, datasets, and tools that power the FOODCAST Price Prediction Platform.
                            </p>
                        </ScrollReveal>
                    </div>
                </section>

                {/* Groups Content */}
                <section className="py-12 sm:py-20">
                    <div className="max-w-7xl mx-auto px-5 lg:px-10 space-y-16 sm:space-y-24">
                        {resourceGroups.map((group, groupIdx) => (
                            <div key={groupIdx}>
                                <ScrollReveal animation="fade-in" delay={100}>
                                    <SectionHeading title={group.title} />
                                </ScrollReveal>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
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
