import Header from "../component/Header";
import Footer from "../component/Footer";
import ScrollReveal from "../component/ScrollReveal";

export default function ResourcesPage() {
    return (
        <>
            <Header />
            <main id="main-content">
                {/* Hero */}
                <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-12 sm:py-14 pt-28 sm:pt-30 overflow-hidden">
                    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                        <div className="absolute top-0 left-1/3 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
                    </div>
                    <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                        <h1
                            className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white mb-2"
                            style={{ fontFamily: "var(--font-display)" }}
                        >
                            Resources & References
                        </h1>
                        <p className="text-white/50 max-w-xl text-sm sm:text-base">
                            Datasets, tools, and technologies used in developing FOODCAST Price Prediction Platform
                        </p>
                    </div>
                </section>

                {/* Main Content */}
                <section className="py-16 sm:py-20 bg-surface">
                    <div className="max-w-7xl mx-auto px-5 lg:px-10">
                        <ScrollReveal animation="fade-in" delay={100}>
                            <div className="mb-12">
                                <h2
                                    className="text-2xl sm:text-3xl lg:text-4xl font-bold text-primary-800 mb-4"
                                    style={{ fontFamily: "var(--font-display)" }}
                                >
                                    Datasets
                                </h2>
                            </div>
                        </ScrollReveal>
                    </div>
                </section>

            </main>
            <Footer />
        </>
    )
}