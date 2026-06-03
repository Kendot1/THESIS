import TagClientView from "../../client/TagClientView";

export default async function TagPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TagClientView tagId={id} />;
}
