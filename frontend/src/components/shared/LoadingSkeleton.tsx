import Skeleton from "@mui/material/Skeleton";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";

export function LoadingSkeleton() {
  return (
    <Box>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, md: 4 }}><Skeleton variant="rounded" height={112} /></Grid>
        <Grid size={{ xs: 12, md: 4 }}><Skeleton variant="rounded" height={112} /></Grid>
        <Grid size={{ xs: 12, md: 4 }}><Skeleton variant="rounded" height={112} /></Grid>
      </Grid>
      <Skeleton variant="rounded" height={300} />
    </Box>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} variant="rounded" height={40} />
      ))}
    </Box>
  );
}
