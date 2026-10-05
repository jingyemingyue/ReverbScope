"""Minimal PySide6 desktop GUI (optional extra ``gui``).

The GUI is a thin front end: it collects files and settings, runs
:func:`reverbscope.core.pipeline.analyze` in a worker thread and displays the
:class:`~reverbscope.models.result.AnalysisResult`. No analysis logic lives here.

Only LGPL-licensed Qt modules (QtCore, QtGui, QtWidgets) are used; plots are
drawn with matplotlib. See docs/DEPENDENCIES.md for the Qt licensing notes.
"""
