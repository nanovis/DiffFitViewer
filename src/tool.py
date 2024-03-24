# vim: set expandtab shiftwidth=4 softtabstop=4:

# === UCSF ChimeraX Copyright ===
# Copyright 2016 Regents of the University of California.
# All rights reserved.  This software provided pursuant to a
# license agreement containing restrictions on its disclosure,
# duplication and use.  For details see:
# http://www.rbvi.ucsf.edu/chimerax/docs/licensing.html
# This notice must be embedded in or attached to all copies,
# including partial copies, of the software or any revisions
# or derivations thereof.
# === UCSF ChimeraX Copyright ===

from .tablemodel import TableModel

from chimerax.core.tools import ToolInstance
from chimerax.core.commands import run
from chimerax.atomic import AtomicStructure
from chimerax.geometry import Place

class TutorialTool(ToolInstance):

    # Inheriting from ToolInstance makes us known to the ChimeraX tool mangager,
    # so we can be notified and take appropriate action when sessions are closed,
    # saved, or restored, and we will be listed among running tools and so on.
    #
    # If cleaning up is needed on finish, override the 'delete' method
    # but be sure to call 'delete' from the superclass at the end.

    SESSION_ENDURING = False    # Does this instance persist when session closes
    SESSION_SAVE = True         # We do save/restore in sessions
    help = "help:user/tools/tutorial.html"
                                # Let ChimeraX know about our help page

    def __init__(self, session, tool_name):
        # 'session'   - chimerax.core.session.Session instance
        # 'tool_name' - string

        # Initialize base class.
        super().__init__(session, tool_name)

        # Set name displayed on title bar (defaults to tool_name)
        # Must be after the superclass init, which would override it.
        self.display_name = "DiffFit Viewer"

        # Create the main window for our tool.  The window object will have
        # a 'ui_area' where we place the widgets composing our interface.
        # The window isn't shown until we call its 'manage' method.
        #
        # Note that by default, tool windows are only hidden rather than
        # destroyed when the user clicks the window's close button.  To change
        # this behavior, specify 'close_destroys=True' in the MainToolWindow
        # constructor.
        from chimerax.ui import MainToolWindow
        self.tool_window = MainToolWindow(self)

        # We will be adding an item to the tool's context menu, so override
        # the default MainToolWindow fill_context_menu method
        self.tool_window.fill_context_menu = self.fill_context_menu

        # Our user interface is simple enough that we could probably inline
        # the code right here, but for any kind of even moderately complex
        # interface, it is probably better to put the code in a method so
        # that this __init__ method remains readable.
        self._build_ui()        

    def _build_ui(self):
        # Put our widgets in the tool window

        # We will use an editable single-line text input field (QLineEdit)
        # with a descriptive text label to the left of it (QLabel).  To
        # arrange them horizontally side by side we use QHBoxLayout
        from Qt.QtWidgets import QLabel, QPushButton, QLineEdit, QVBoxLayout, QTableView        

        layout = QVBoxLayout()        

        # root folder
        layout.addWidget(QLabel("Specify the root directory (containing 'src' folder):"))
        self.init_folder = QLineEdit()
        self.init_folder.setText('D:\GIT\DiffFitViewer')
        self.init_folder.returnPressed.connect(self.return_pressed)
        layout.addWidget(self.init_folder)

        # init button
        button = QPushButton()
        button.setText("Init")
        button.clicked.connect(self.init_button_clicked)

        layout.addWidget(button)        

        # Arrange for our 'return_pressed' method to be called when the
        # user presses the Return key
        #layout.addWidget(QLabel("Log this text:"))
        #self.line_edit = QLineEdit()
        #self.line_edit.returnPressed.connect(self.return_pressed)
        #layout.addWidget(self.line_edit)

        view = QTableView();
        view.resize(800, 500)
        view.horizontalHeader().setStretchLastSection(True)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.clicked.connect(self.table_row_clicked)        
        layout.addWidget(view)
        self.view = view

        stats = QLabel()
        stats.setText("stats: ")
        layout.addWidget(stats)
        self.stats = stats
        
        # Set the layout as the contents of our window
        self.tool_window.ui_area.setLayout(layout)

        # Show the window on the user-preferred side of the ChimeraX
        # main window
        self.tool_window.manage('side')

    def return_pressed(self):
        #from Qt.QtWidgets import QFileDialog
        
        #folderpath = QFileDialog.getExistingDirectory(self, 'Select Folder')
        #print(folderpath)
        
        # The use has pressed the Return key; log the current text as HTML

        # ToolInstance has a 'session' attribute...
        run(self.session, "log html %s" % self.init_folder.text())            

    def fill_context_menu(self, menu, x, y):
        # Add any tool-specific items to the given context menu (a QMenu instance).
        # The menu will then be automatically filled out with generic tool-related actions
        # (e.g. Hide Tool, Help, Dockable Tool, etc.) 
        #
        # The x,y args are the x() and y() values of QContextMenuEvent, in the rare case
        # where the items put in the menu depends on where in the tool interface the menu
        # was raised.
        from Qt.QtGui import QAction
        clear_action = QAction("Clear", menu)
        clear_action.triggered.connect(lambda *args: self.init_folder.clear())
        menu.addAction(clear_action)
        
    def table_row_clicked(self, item):
        from .parse_log import cluster_and_sort_sqd, look_at_cluster, look_at_MQS_idx
    
        if item.row() != -1:
            self.cluster_idx = item.row()
            look_at_cluster(self.e_sqd_clusters_ordered, self.mol_folder, self.cluster_idx, self.session)
            
    
    def init_button_clicked(self):
        root = self.init_folder.text()
        
        if len(root) == 0:
            print("Specify the root folder first!")
            return
        
        #root = 'D:\\Research\\IPM\\PoseEstimation\\DiffFitViewer\\script'
        #root = 'D:\GIT\DiffFitViewer'
        
        import sys
        sys.path.append(root + '\\script')
        from .parse_log import cluster_and_sort_sqd, look_at_cluster, look_at_MQS_idx
        import numpy as np
        from chimerax.core.commands import run
        import os

        print("opening the volume")
        vol_path = root + "\dev_data\input\domain_fit_demo_3domains\density2.mrc"
        vol = run(self.session, f"open {vol_path}")[0]

        print("computing clusters")
        e_sqd_log = np.load(root + "\dev_data\output\dev_comp_domain_fit_3_domains\e_sqd_log.npy")
        self.e_sqd_clusters_ordered = cluster_and_sort_sqd(e_sqd_log)

        from Qt.QtCore import QSortFilterProxyModel, Qt
        model = TableModel(self.e_sqd_clusters_ordered)
        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(model)
        
        self.view.setModel(proxyModel)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.DescendingOrder)
        self.view.reset()
        self.view.show()  
        
        self.stats.setText("stats: {0} entries".format(model.rowCount())) 
        
        print("showing the first cluster")
        self.mol_folder = root + "\dev_data\input\domain_fit_demo_3domains\subunits_cif"        
        self.cluster_idx = 0
        look_at_cluster(self.e_sqd_clusters_ordered, self.mol_folder, self.cluster_idx, self.session)