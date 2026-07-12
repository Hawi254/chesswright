export default function PageStub({ title }: { title: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text">{title}</h1>
      <p className="mt-2 text-text-muted">Not yet migrated to the new interface.</p>
    </div>
  )
}
