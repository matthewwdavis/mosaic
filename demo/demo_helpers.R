# Helpers for demo_plots.R: tight margins (fit_margins, copied from Bushy_Top/Scripts/phylogeny_bootstrap_v6.Rmd with
# one change, at step 4) and saving a figure as PDF, PNG and SVG

fit_margins <- function(plot, width = NULL, height = NULL, sides = c("t", "r", "b", "l"), pad_pt = 0.5, res = 300) {
  # Smallest plot margins that keep everything inside the figure. The plot is drawn at its saved size on a transparent
  # canvas with room around it, so nothing is cut at the figure's edges, and each side in `sides` gets a margin just big
  # enough for whatever reaches past that edge (tick labels, titles, icons, circles or text drawn outside the panel), plus
  # pad_pt; every other side gets no margin. width / height: the size the figure is saved at (in), with a panel that
  # stretches to fill it; the margins are re-measured until they settle, since a narrower panel moves what's drawn past it.
  # NULL: a fixed-size figure (fixed panel), whose size is added up from the plot and rounded up to whole points, the extra
  # going in the right / top margin so the plot doesn't move from the bottom-left corner. pdf() cuts the page down to whole
  # points at the top and right, so for a given size those edges are measured from the cut.
  # Returns the plot with its new margins, the size to save it at, and the margins (in)
  margins <- c(t = 0, r = 0, b = 0, l = 0)
  old_dev <- grDevices::dev.cur()
  set_margins <- function(m) {
    plot + ggplot2::theme(plot.margin = ggplot2::margin(m[["t"]], m[["r"]], m[["b"]], m[["l"]], unit = "in"))
  }
  added_up <- function(g) {
    c(w = sum(grid::convertWidth(g$widths, "in", valueOnly = TRUE)),
      h = sum(grid::convertHeight(g$heights, "in", valueOnly = TRUE)))
  }
  ink_edges <- function(g, w, h, room, dpi) {
    # draw g at w x h in, with `room` in of transparent canvas on every side; returns how far the ink (anything not fully
    # transparent) reaches, in inches from the figure's bottom-left corner, and whether it touches the canvas's edge
    cap <- ragg::agg_capture(width = w + 2 * room, height = h + 2 * room, units = "in", res = dpi, background = "transparent")
    grid::pushViewport(grid::viewport(x = grid::unit(room, "in"), y = grid::unit(room, "in"),
                                      width = grid::unit(w, "in"), height = grid::unit(h, "in"), just = c("left", "bottom")))
    grid::grid.draw(g)
    px <- cap(native = TRUE)
    grDevices::dev.off()
    if (old_dev > 1) grDevices::dev.set(old_dev)
    # a nativeRaster is stored row by row, top row first, one integer per pixel (0 = fully transparent; a half-transparent
    # black pixel reads as NA, so it counts as ink too)
    px_dim <- dim(px)
    px <- as.vector(unclass(px))
    ink <- matrix(is.na(px) | px != 0L, nrow = px_dim[1], ncol = px_dim[2], byrow = TRUE)
    rows <- which(rowSums(ink) > 0)
    cols <- which(colSums(ink) > 0)
    if (!length(rows)) return(list(edges = c(t = h, r = w, b = 0, l = 0), touches = FALSE))
    return(list(edges = c(t = h + room - (min(rows) - 1) / dpi,
                          r = max(cols) / dpi - room,
                          b = h + room - max(rows) / dpi,
                          l = (min(cols) - 1) / dpi - room),
                touches = min(rows) == 1 || max(rows) == nrow(ink) || min(cols) == 1 || max(cols) == ncol(ink)))
  }
  for (i in 1:6) {
    # 1. The plot with the current margins, no plot background (it would count as ink)
    g <- ggplot2::ggplotGrob(set_margins(margins) + ggplot2::theme(plot.background = ggplot2::element_blank()))
    w <- if (is.null(width)) added_up(g)[["w"]] else width
    h <- if (is.null(height)) added_up(g)[["h"]] else height

    # 2. Rough look with 8 in of room (doubled while anything reaches the canvas's edge), to see how far things reach; then a
    #    fine look with just that much room, plus a little. ragg skips text under ~8 px tall, so 200 dpi (the rough look)
    #    still draws text down to ~2.9 pt, and res = 300 (the fine look) down to ~1.9 pt. Anything lying wholly more than
    #    8 in past the figure's edge never reaches the rough canvas, so it isn't seen
    room <- 8
    repeat {
      rough <- ink_edges(g, w, h, room, dpi = 200)
      if (!rough$touches) break
      if (room >= 64) stop("something reaches more than 64 in past the figure's edge")
      room <- room * 2
    }
    reach <- max(0, rough$edges[["t"]] - h, rough$edges[["r"]] - w, -rough$edges[["b"]], -rough$edges[["l"]])
    edges <- ink_edges(g, w, h, room = reach + 0.25, dpi = res)$edges

    # 3. How far the ink reaches past each edge (in; negative = room to spare); for a given size, the top and right edges
    #    are where pdf() cuts the page
    page_top <- if (is.null(height)) h else floor(h * 72 + 1e-6) / 72
    page_right <- if (is.null(width)) w else floor(w * 72 + 1e-6) / 72
    past <- c(t = edges[["t"]] - page_top,
              r = edges[["r"]] - page_right,
              b = -edges[["b"]],
              l = -edges[["l"]])

    # 4. New margins: the edge pad_pt outside the ink, on every fitted side; no margin on sides not fitted. (Changed for
    #    the demo: the original gave no margin wherever the ink fitted without one, so ink closer than pad_pt to the edge
    #    got no pad, and ink further in left a wider gap. A negative margin pulls the edge in to the ink)
    need <- margins + past
    new <- need + pad_pt / 72
    new[!names(new) %in% sides] <- 0
    settled <- max(abs(new - margins)) < 0.05 / 72
    margins <- new
    if (settled) break
  }

  # 5. A size added up from the plot, rounded up to whole points: the extra goes in the right / top margin
  raw <- added_up(ggplot2::ggplotGrob(set_margins(margins)))
  size_pt <- ceiling(raw * 72 - 1e-6)
  if (is.null(width)) margins[["r"]] <- margins[["r"]] + size_pt[["w"]] / 72 - raw[["w"]]
  if (is.null(height)) margins[["t"]] <- margins[["t"]] + size_pt[["h"]] / 72 - raw[["h"]]
  fitted <- set_margins(margins)

  # 6. Size to save at: whole points plus a hair (0.001 pt), since pdf() truncates the page size to whole points and a sum
  #    can come out a hair under (32.99999 pt -> a 32 pt page)
  size <- c(w = if (is.null(width)) (size_pt[["w"]] + 0.001) / 72 else width,
            h = if (is.null(height)) (size_pt[["h"]] + 0.001) / 72 else height)
  return(list(plot = fitted, width = size[["w"]], height = size[["h"]], margins_in = margins))
}

save_figure <- function(plot, stem, size_mm) {
  # Save a plot as stem.pdf, stem.png (600 dpi) and stem.svg, size_mm = c(width = , height = ) in mm, with transparent
  # backgrounds and margins 0.5 pt outside the ink. Returns the size saved at, in pt

  # 1. The page in whole points, rounded up (pdf() cuts a page down to whole points), plus a hair so it isn't cut short
  size_pt <- ceiling(size_mm / 25.4 * 72 - 1e-6)
  width_in <- (size_pt[["width"]] + 0.001) / 72
  height_in <- (size_pt[["height"]] + 0.001) / 72

  # 2. Margins measured to the ink, 0.5 pt outside it
  fit <- fit_margins(plot, width = width_in, height = height_in, pad_pt = 0.5, res = 2400)

  # 3. The three copies, all the same size; the SVG is the one for PowerPoint
  dir.create(dirname(stem), recursive = TRUE, showWarnings = FALSE)
  ggplot2::ggsave(paste0(stem, ".pdf"), fit$plot, width = fit$width, height = fit$height, bg = "transparent")
  ggplot2::ggsave(paste0(stem, ".png"), fit$plot, width = fit$width, height = fit$height, dpi = 600, bg = "transparent")
  ggplot2::ggsave(paste0(stem, ".svg"), fit$plot, width = fit$width, height = fit$height, bg = "transparent")
  message(sprintf("Saved %s (.pdf .png .svg), %d x %d pt", stem, size_pt[["width"]], size_pt[["height"]]))
  return(invisible(size_pt))
}
