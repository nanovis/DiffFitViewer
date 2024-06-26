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

from Qt.QtWidgets import QLabel, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox
from Qt.QtWidgets import QTableView, QSlider, QTabWidget, QGroupBox, QDoubleSpinBox, QSpinBox 
from Qt.QtWidgets import QFileDialog
from Qt.QtCore import QSortFilterProxyModel, Qt

from chimerax.core.tools import ToolInstance
from chimerax.core.commands import run
from chimerax.map.volume import volume_list
from chimerax.atomic import AtomicStructure
from chimerax.geometry import Place
from chimerax.ui import MainToolWindow

from .parse_log import look_at_record, look_at_cluster, look_at_MQS_idx, animate_MQS, animate_MQS_2
from .parse_log import simulate_volume, get_transformation_at_record, zero_cluster_density
from .tablemodel import TableModel
from .DiffAtomComp import diff_atom_comp, cluster_and_sort_sqd_fast

import sys
import numpy as np        
import os
        
        
class DiffFitSettings:    
    def __init__(self):   
        # viewing
        self.view_output_directory: str = "D:\\GIT\\DiffFitViewer\\dev_data\\output\\dev_comp_domain_fit_3_domains_10s20q_new_q"
        self.view_target_vol_path: str = "D:\\GIT\\DiffFitViewer\\dev_data\\input\\domain_fit_demo_3domains\\density2.mrc"        
        self.view_structures_directory: str = "D:\\GIT\\DiffFitViewer\dev_data\input\domain_fit_demo_3domains\subunits_cif"
        
        # computing
        self.input_directory: str = "D:\\GIT\\DiffFitViewer\\dev_data\\input\\domain_fit_demo_3domains"        
        self.target_vol_path: str = "D:\\GIT\\DiffFitViewer\\dev_data\\input\\domain_fit_demo_3domains\\density2.mrc"        
        self.structures_directory: str = "D:\\GIT\\DiffFitViewer\dev_data\input\domain_fit_demo_3domains\subunits_cif"
        self.structures_sim_map_dir: str = "D:\\GIT\\DiffFitViewer\dev_data\input\domain_fit_demo_3domains\subunits_mrc"
        
        self.output_directory: str = "D:\\GIT\\DiffFitViewer\\dev_data\\output"
        self.exp_name: str = "dev_comp"
        
        self.target_surface_threshold: float = 0.7
        self.min_cluster_size: float = 100
        self.N_shifts: int = 10
        self.N_quaternions: int = 100
        self.negative_space_value: float = -0.5
        self.learning_rate: float = 0.01
        self.N_iters: int = 201        
        self.out_dir_exist_ok: bool = True
        self.conv_loops: int = 10
        self.conv_kernel_sizes: list = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5]
        self.conv_weights: list = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        
        self.clustering_shift_tolerance : float = 3.0
        self.clustering_angle_tolerance : float = 6.0


class DiffFitTool(ToolInstance):

    # Inheriting from ToolInstance makes us known to the ChimeraX tool mangager,
    # so we can be notified and take appropriate action when sessions are closed,
    # saved, or restored, and we will be listed among running tools and so on.
    #
    # If cleaning up is needed on finish, override the 'delete' method
    # but be sure to call 'delete' from the superclass at the end.

    SESSION_ENDURING = False    # Does this instance persist when session closes
    SESSION_SAVE = True         # We do save/restore in sessions
    help = "help:user/tools/DiffFit.html"
                                # Let ChimeraX know about our help page

    def __init__(self, session, tool_name):
        # 'session'   - chimerax.core.session.Session instance
        # 'tool_name' - string

        # Initialize base class.
        super().__init__(session, tool_name)

        # Set name displayed on title bar (defaults to tool_name)
        # Must be after the superclass init, which would override it.
        self.display_name = "DiffFit"
        self.settings = DiffFitSettings()
        
        # Create the main window for our tool.  The window object will have
        # a 'ui_area' where we place the widgets composing our interface.
        # The window isn't shown until we call its 'manage' method.
        #
        # Note that by default, tool windows are only hidden rather than
        # destroyed when the user clicks the window's close button.  To change
        # this behavior, specify 'close_destroys=True' in the MainToolWindow
        # constructor.        
        self.tool_window = MainToolWindow(self)

        # We will be adding an item to the tool's context menu, so override
        # the default MainToolWindow fill_context_menu method
        #self.tool_window.fill_context_menu = self.fill_context_menu

        # Our user interface is simple enough that we could probably inline
        # the code right here, but for any kind of even moderately complex
        # interface, it is probably better to put the code in a method so
        # that this __init__ method remains readable.
        self._build_ui()        

    def _build_ui(self):
        
        # the base layout is Vertical
        
        tab_widget = QTabWidget()
        tab_widget.setTabPosition(QTabWidget.West)

        # single fit GUI
        single_fit_group = QGroupBox()
        single_fit_group_layout = QGridLayout()
        single_fit_group.setLayout(single_fit_group_layout)
        self.build_single_fit_ui(single_fit_group_layout)
        tab_widget.addTab(single_fit_group, "Single")

        # computation GUI
        compute_group = QGroupBox()
        compute_group_layout = QGridLayout()
        compute_group.setLayout(compute_group_layout)
        self.build_compute_ui(compute_group_layout)
        tab_widget.addTab(compute_group, "Compute")
    
        # view GUI
        view_group = QGroupBox()
        view_group_layout = QGridLayout()
        view_group.setLayout(view_group_layout)
        self.build_view_ui(view_group_layout)
        tab_widget.addTab(view_group, "View")
        
        # TODO: place where to update the settings
        self.load_settings()
        
        # Set the layout as the contents of our window        
        layout = QVBoxLayout()                
        layout.addWidget(tab_widget)
        self.tool_window.ui_area.setLayout(layout)
        
        # Show the window on the user-preferred side of the ChimeraX
        # main window
        self.tool_window.manage('side')

    def load_settings(self):
        print("loading settings...")
        
        self.settings.loading = True
    
        #compute
        self.target_vol_path.setText(self.settings.target_vol_path)
        self.structures_dir.setText(self.settings.structures_directory)
        self.structures_sim_map_dir.setText(self.settings.structures_sim_map_dir)
        self.out_dir.setText(self.settings.output_directory)
        self.exp_name.setText(self.settings.exp_name)        
        self.target_surface_threshold.setValue(self.settings.target_surface_threshold)
        self.min_cluster_size.setValue(self.settings.min_cluster_size)
        self.n_iters.setValue(self.settings.N_iters)
        self.n_shifts.setValue(self.settings.N_shifts)
        self.n_quaternions.setValue(self.settings.N_quaternions)        
        self.negative_space_value.setValue(self.settings.negative_space_value)
        self.learning_rate.setValue(self.settings.learning_rate)
        self.conv_loops.setValue(self.settings.conv_loops)
        self.conv_kernel_sizes.setText("[{0}]".format(','.join(map(str, self.settings.conv_kernel_sizes))))
        self.conv_weights.setText("[{0}]".format(','.join(map(str, self.settings.conv_weights))))
        
        # view
        self.target_vol.setText(self.settings.view_target_vol_path)     
        self.dataset_folder.setText(self.settings.view_output_directory)        
        self.structures_folder.setText(self.settings.view_structures_directory)        
        
        # clustering
        self.clustering_angle_tolerance.setValue(self.settings.clustering_angle_tolerance)
        self.clustering_shift_tolerance.setValue(self.settings.clustering_shift_tolerance)
        
        self.settings.loading = False
    
    def store_settings(self):    
        #print("settings changed...")
        
        if self.settings.loading :
            return
        
        #compute
        self.settings.target_vol_path = self.target_vol_path.text()
        self.settings.structures_directory = self.structures_dir.text()
        self.settings.structures_sim_map_dir = self.structures_sim_map_dir.text()
        self.settings.output_directory = self.out_dir.text()        
        self.settings.exp_name = self.exp_name.text()        
        self.settings.target_surface_threshold = self.target_surface_threshold.value()
        self.settings.min_cluster_size = self.min_cluster_size.value()
        self.settings.N_iters = self.n_iters.value()
        self.settings.N_shifts = self.n_shifts.value()
        self.settings.N_quaternions = self.n_quaternions.value()        
        self.settings.negative_space_value = self.negative_space_value.value()
        self.settings.learning_rate = self.learning_rate.value()
        self.settings.conv_loops = self.conv_loops.value()
        
        kernel_sizes = self.conv_kernel_sizes.text().replace(" ", "").strip('][').split(',')
        self.settings.conv_kernel_sizes = [int(s) for s in kernel_sizes]
        
        weights = self.conv_weights.text().replace(" ", "").strip('][').split(',')
        self.settings.conv_weights = [float(s) for s in kernel_sizes]
        
        #view
        self.settings.view_output_directory = self.dataset_folder.text()
        self.settings.view_structures_directory = self.structures_folder.text()
        self.settings.view_target_vol_path = self.target_vol.text()
        
        # clustering
        self.settings.clustering_angle_tolerance = self.clustering_angle_tolerance.value()
        self.settings.clustering_shift_tolerance = self.clustering_shift_tolerance.value()
        
        #print(self.settings)
        #print(self.settings.view_target_vol_path)

    def build_single_fit_ui(self, layout):
        row = 0

        mol_label = QLabel()
        mol_label.setText("Fit")

        layout.addWidget(mol_label, row, 0)

        from chimerax.map import Volume
        from chimerax.atomic import Structure
        from chimerax.ui.widgets import ModelMenuButton
        self._object_menu = om = ModelMenuButton(self.session, class_filter=Structure)
        mlist = self.session.models.list(type=Structure)
        vlist = self.session.models.list(type=Volume)
        if mlist:
            om.value = mlist[0]
        # om.value_changed.connect(self._object_chosen)
        layout.addWidget(om, row, 1)

        iml = QLabel("in map")
        layout.addWidget(iml, row, 2)

        self._map_menu = mm = ModelMenuButton(self.session, class_filter=Volume)
        if vlist:
            mm.value = vlist[0]
        layout.addWidget(mm, row, 3)

        row = row + 1


    def build_compute_ui(self, layout):
        row = 0
               
        target_vol_path_label = QLabel()
        target_vol_path_label.setText("Target Volume:")
        self.target_vol_path = QLineEdit()
        self.target_vol_path.textChanged.connect(lambda: self.store_settings())                
        target_vol_path_select = QPushButton("Select")        
        target_vol_path_select.clicked.connect(lambda: self.select_clicked("Target Volume", self.target_vol_path, False, "MRC Files(*.mrc);;MAP Files(*.map)"))        
        layout.addWidget(target_vol_path_label, row, 0)
        layout.addWidget(self.target_vol_path, row, 1)
        layout.addWidget(target_vol_path_select, row, 2)
        row = row + 1
        
        structures_dir_label = QLabel()
        structures_dir_label.setText("Structures Folder:")
        self.structures_dir = QLineEdit()
        self.structures_dir.textChanged.connect(lambda: self.store_settings())    
        structures_dir_select = QPushButton("Select")        
        structures_dir_select.clicked.connect(lambda: self.select_clicked("Structures folder (containing *.cif)", self.structures_dir))
        layout.addWidget(structures_dir_label, row, 0)
        layout.addWidget(self.structures_dir, row, 1)
        layout.addWidget(structures_dir_select, row, 2)
        row = row + 1
        
        structures_sim_map_dir_label = QLabel()
        structures_sim_map_dir_label.setText("Structures sim-map Folder:")
        self.structures_sim_map_dir = QLineEdit()
        self.structures_sim_map_dir.textChanged.connect(lambda: self.store_settings())   
        structures_sim_map_dir_select = QPushButton("Select")        
        structures_sim_map_dir_select.clicked.connect(lambda: self.select_clicked("Structures sim-map Folder", self.structures_sim_map_dir))
        layout.addWidget(structures_sim_map_dir_label, row, 0)
        layout.addWidget(self.structures_sim_map_dir, row, 1)
        layout.addWidget(structures_sim_map_dir_select, row, 2)
        row = row + 1
        
        out_dir_label = QLabel()
        out_dir_label.setText("Output Folder:")
        self.out_dir = QLineEdit()
        self.out_dir.textChanged.connect(lambda: self.store_settings()) 
        out_dir_select = QPushButton("Select")        
        out_dir_select.clicked.connect(lambda: self.select_clicked("Output Folder", self.out_dir))        
        layout.addWidget(out_dir_label, row, 0)
        layout.addWidget(self.out_dir, row, 1)
        layout.addWidget(out_dir_select, row, 2)
        row = row + 1
        
        exp_name_label = QLabel()
        exp_name_label.setText("Experiment name:")
        self.exp_name = QLineEdit()
        self.exp_name.textChanged.connect(lambda: self.store_settings())        
        layout.addWidget(exp_name_label, row, 0)
        layout.addWidget(self.exp_name, row, 1, 1, 2)
        row = row + 1
        
        target_surface_threshold_label = QLabel()
        target_surface_threshold_label.setText("Target surface threshold:")
        self.target_surface_threshold = QDoubleSpinBox()
        self.target_surface_threshold.setMinimum(0.0)
        self.target_surface_threshold.setMaximum(20.0)
        self.target_surface_threshold.setSingleStep(0.01)
        self.target_surface_threshold.setDecimals(4)
        self.target_surface_threshold.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(target_surface_threshold_label, row, 0)
        layout.addWidget(self.target_surface_threshold, row, 1, 1, 2)
        row = row + 1
        
        min_cluster_size_label = QLabel()
        min_cluster_size_label.setText("Min island size:")
        self.min_cluster_size = QSpinBox()
        self.min_cluster_size.setMinimum(1)
        self.min_cluster_size.setMaximum(500)
        self.min_cluster_size.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(min_cluster_size_label, row, 0)
        layout.addWidget(self.min_cluster_size, row, 1, 1, 2)
        row = row + 1
        
        
        # advanced
        # TODO:
        n_iters_label = QLabel()
        n_iters_label.setText("# iters:")
        self.n_iters = QSpinBox()
        self.n_iters.setMinimum(1)
        self.n_iters.setMaximum(500)
        self.n_iters.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(n_iters_label, row, 0)
        layout.addWidget(self.n_iters, row, 1, 1, 2)
        row = row + 1
        
        n_shifts_label = QLabel()
        n_shifts_label.setText("# shifts:")
        self.n_shifts = QSpinBox()
        self.n_shifts.setMinimum(1)
        self.n_shifts.setMaximum(500)
        self.n_shifts.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(n_shifts_label, row, 0)
        layout.addWidget(self.n_shifts, row, 1, 1, 2)
        row = row + 1
        
        n_quaternions_label = QLabel()
        n_quaternions_label.setText("# quaternions:")
        self.n_quaternions = QSpinBox()
        self.n_quaternions.setMinimum(1)
        self.n_quaternions.setMaximum(500)
        self.n_quaternions.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(n_quaternions_label, row, 0)
        layout.addWidget(self.n_quaternions, row, 1, 1, 2)
        row = row + 1
        
        negative_space_value_label = QLabel()
        negative_space_value_label.setText("Negative space value:")
        self.negative_space_value = QDoubleSpinBox()
        self.negative_space_value.setMinimum(-100)
        self.negative_space_value.setMaximum(100)
        self.negative_space_value.setSingleStep(0.1)
        self.negative_space_value.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(negative_space_value_label, row, 0)
        layout.addWidget(self.negative_space_value, row, 1, 1, 2)
        row = row + 1
        
        learning_rate_label = QLabel()
        learning_rate_label.setText("Learning rate:")
        self.learning_rate = QDoubleSpinBox()
        self.learning_rate.setMinimum(0.00001)
        self.learning_rate.setMaximum(10)
        self.learning_rate.setSingleStep(0.01)
        self.learning_rate.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(learning_rate_label, row, 0)
        layout.addWidget(self.learning_rate, row, 1, 1, 2)
        row = row + 1
        
        convs_loops_label = QLabel()
        convs_loops_label.setText("Conv. loops:")
        self.conv_loops = QSpinBox()
        self.conv_loops.setMinimum(1)
        self.conv_loops.setMaximum(500)
        self.conv_loops.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(convs_loops_label, row, 0)
        layout.addWidget(self.conv_loops, row, 1, 1, 2)
        row = row + 1
        
        conv_kernel_sizes_label = QLabel()
        conv_kernel_sizes_label.setText("Conv. kernel sizes [list]:")
        self.conv_kernel_sizes = QLineEdit()
        self.conv_kernel_sizes.setText("[5, 5, 5, 5, 5, 5, 5, 5, 5, 5]")
        self.conv_kernel_sizes.textChanged.connect(lambda: self.store_settings())        
        layout.addWidget(conv_kernel_sizes_label, row, 0)
        layout.addWidget(self.conv_kernel_sizes, row, 1, 1, 2)
        row = row + 1
        
        conv_weights_label = QLabel()
        conv_weights_label.setText("Conv. weights [list]:")
        self.conv_weights = QLineEdit()
        self.conv_weights.setText("[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]")
        self.conv_weights.textChanged.connect(lambda: self.store_settings())        
        layout.addWidget(conv_weights_label, row, 0)
        layout.addWidget(self.conv_weights, row, 1, 1, 2)
        row = row + 1
        
        #conv_weights_label = QCheckBox()
        #conv_weights_label.setText("Visualize results:")
        #self.conv_weights = QLineEdit()
        #self.conv_weights.setText("[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]")
        #self.conv_weights.textChanged.connect(lambda: self.store_settings())        
        #layout.addWidget(conv_weights_label, row, 0)
        #layout.addWidget(self.conv_weights, row, 1, 1, 2)
        #row = row + 1
        
        
        button = QPushButton()
        button.setText("Run!")
        button.clicked.connect(lambda: self.run_button_clicked())        
        layout.addWidget(button, row, 1, 1, 2)        


    def build_view_ui(self, layout):
        row = 0
            
        #self.view_target_vol_path: str = "..."        
        target_vol_label = QLabel("Target Volume:")
        self.target_vol = QLineEdit()        
        self.target_vol.textChanged.connect(lambda: self.store_settings())
        target_vol_select = QPushButton("Select")        
        target_vol_select.clicked.connect(lambda: self.select_clicked("Target Volume", self.target_vol, False, "MRC Files(*.mrc);;MAP Files(*.map)"))        
        layout.addWidget(target_vol_label, row, 0)
        layout.addWidget(self.target_vol, row, 1)
        layout.addWidget(target_vol_select, row, 2)
        row = row + 1
        
        # self.view_structures_directory: str = "..."              
        structures_folder_label = QLabel("Structures Folder:")
        self.structures_folder = QLineEdit()
        self.structures_folder.textChanged.connect(lambda: self.store_settings()) 
        structures_folder_select = QPushButton("Select")        
        structures_folder_select.clicked.connect(lambda: self.select_clicked("Structures folder (containing *.cif)", self.structures_folder))                
        layout.addWidget(structures_folder_label, row, 0)
        layout.addWidget(self.structures_folder, row, 1)
        layout.addWidget(structures_folder_select, row, 2)
        row = row + 1
        
        # data folder - where the data is stored
        dataset_folder_label = QLabel("Data Folder:")
        self.dataset_folder = QLineEdit()    
        self.dataset_folder.textChanged.connect(lambda: self.store_settings())                
        dataset_folder_select = QPushButton("Select")        
        dataset_folder_select.clicked.connect(lambda: self.select_clicked("Data Folder", self.dataset_folder))        
        layout.addWidget(dataset_folder_label, row, 0)
        layout.addWidget(self.dataset_folder, row, 1)
        layout.addWidget(dataset_folder_select, row, 2)
        row = row + 1
        
        clustering_shift_tolerance_label = QLabel()
        clustering_shift_tolerance_label.setText("Clustering - Shift Tolerance:")
        self.clustering_shift_tolerance = QDoubleSpinBox()
        self.clustering_shift_tolerance.setMinimum(0.0)
        self.clustering_shift_tolerance.setMaximum(100)
        self.clustering_shift_tolerance.setSingleStep(1.0)
        self.clustering_shift_tolerance.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(clustering_shift_tolerance_label, row, 0)
        layout.addWidget(self.clustering_shift_tolerance, row, 1, 1, 2)
        row = row + 1
                
        clustering_angle_tolerance_label = QLabel()
        clustering_angle_tolerance_label.setText("Clustering - Angle Tolerance:")
        self.clustering_angle_tolerance = QDoubleSpinBox()
        self.clustering_angle_tolerance.setMinimum(0.0)
        self.clustering_angle_tolerance.setMaximum(180)
        self.clustering_angle_tolerance.setSingleStep(1.0)
        self.clustering_angle_tolerance.valueChanged.connect(lambda: self.store_settings())        
        layout.addWidget(clustering_angle_tolerance_label, row, 0)
        layout.addWidget(self.clustering_angle_tolerance, row, 1, 1, 2)
        row = row + 1
        
        # init button                
        button = QPushButton()
        button.setText("Load")
        button.clicked.connect(lambda: self.init_button_clicked())        
        layout.addWidget(button, row, 1, 1, 2)
        row = row + 1        

        # Arrange for our 'return_pressed' method to be called when the
        # user presses the Return key
        #layout.addWidget(QLabel("Log this text:"))
        #self.line_edit = QLineEdit()
        #self.line_edit.returnPressed.connect(self.return_pressed)
        #layout.addWidget(self.line_edit)

        # table view of all the results
        view = QTableView()
        view.resize(800, 500)
        view.horizontalHeader().setStretchLastSection(True)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.clicked.connect(self.table_row_clicked)        
        layout.addWidget(view)        
        self.view = view
        layout.addWidget(view, row, 0, 1, 3)
        row = row + 1        

        # simple label for simple statistics
        stats = QLabel()
        stats.setText("Stats: ")
        self.stats = stats
        layout.addWidget(stats, row, 0, 1, 3)
        row = row + 1        
        
        # button panel                
        simulate_volume_label = QLabel("Resolution:")        
        self.simulate_volume_resolution = QDoubleSpinBox()
        self.simulate_volume_resolution.setMinimum(0.001)
        self.simulate_volume_resolution.setMaximum(100.0)
        self.simulate_volume_resolution.setSingleStep(0.1)
        self.simulate_volume_resolution.setValue(4.0)        
        simulate_volume = QPushButton()
        simulate_volume.setText("Simulate Volume")
        simulate_volume.clicked.connect(self.simulate_volume_clicked)        
        layout.addWidget(simulate_volume_label, row, 0)
        layout.addWidget(self.simulate_volume_resolution, row, 1)
        layout.addWidget(simulate_volume, row, 2)
        row = row + 1        
        
        zero_density_button = QPushButton()
        zero_density_button.setText("Zero density")
        zero_density_button.clicked.connect(self.zero_density_button_clicked)
        
        # saving currently selected object
        save_button = QPushButton()
        save_button.setText("Save")
        save_button.clicked.connect(self.save_button_clicked)
        layout.addWidget(zero_density_button, row, 1)
        layout.addWidget(save_button, row, 2)
        row = row + 1        
        
        # slider for animation
        progress_label1 = QLabel()
        progress_label1.setText("Step: ")

        progress = QSlider(Qt.Horizontal)
        progress.setTickPosition(QSlider.TicksBelow)
        progress.setTickInterval(1) 
        progress.setMinimum(1)
        progress.setMaximum(1)
        progress.valueChanged.connect(self.progress_value_changed)        
        self.progress = progress              
        
        progress_label = QLabel()
        progress_label.setText("1/1")
        self.progress_label = progress_label

        layout.addWidget(progress_label1, row, 0)
        layout.addWidget(progress, row, 1)
        layout.addWidget(progress_label, row, 2)
        row = row + 1        
        
    #def fill_context_menu(self, menu, x, y):
        # Add any tool-specific items to the given context menu (a QMenu instance).
        # The menu will then be automatically filled out with generic tool-related actions
        # (e.g. Hide Tool, Help, Dockable Tool, etc.) 
        #
        # The x,y args are the x() and y() values of QContextMenuEvent, in the rare case
        # where the items put in the menu depends on where in the tool interface the menu
        # was raised.
        #from Qt.QtGui import QAction
        #clear_action = QAction("Clear", menu)
        #clear_action.triggered.connect(lambda *args: self.init_folder.clear())
        #menu.addAction(clear_action)
        
    def table_row_clicked(self, item):        
    
        if item.row() != -1:
            proxyIndex = self.proxyModel.index(item.row(), 0)
            sourceIndex = self.proxyModel.mapToSource(proxyIndex)
            self.cluster_idx = sourceIndex.row()

            self.mol_idx = int(self.e_sqd_clusters_ordered[self.cluster_idx, 0])
            self.record_idx = int(self.e_sqd_clusters_ordered[self.cluster_idx, 1])

            N_iter = len(self.e_sqd_log[self.mol_idx, self.record_idx])
            iter_idx = int(self.e_sqd_clusters_ordered[self.cluster_idx, 2])

            self.transformation = get_transformation_at_record(self.e_sqd_log, self.mol_idx, self.record_idx, iter_idx)
            self.mol = look_at_record(self.mol_folder, self.mol_idx, self.transformation, self.session)

            self.session.logger.info(f"Cluster size: {int(self.e_sqd_clusters_ordered[self.cluster_idx, 3])}")
            self.session.logger.info(f"Highest metric reached at iter : {iter_idx}")

            self.progress.setMinimum(1)
            self.progress.setMaximum(N_iter)
            self.progress.setValue(iter_idx)
        
    def select_clicked(self, text, target, save = False, pattern = "dir"):
        fileName = ""
        ext = ""
        
        if save:
            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog
            fileName, ext = QFileDialog.getSaveFileName(target, text, "", pattern, options = options)
            ext = ext[-4:]
            ext = ext[:3]                
        else:
            if pattern == "dir":
                fileName = QFileDialog.getExistingDirectory(target, text)
            elif len(pattern) > 0 :
                options = QFileDialog.Options()
                options |= QFileDialog.DontUseNativeDialog
                fileName, ext = QFileDialog.getOpenFileName(target, text, "", pattern, options = options)   
                ext = ext[-4:]
                ext = ext[:3]                
                
            if len(fileName) > 0:
                print("settings to GUI")
                print(fileName)
                target.setText(fileName)
            
        return fileName, ext
    
    def show_results(self, e_sqd_log):
        if e_sqd_log is None:
            return

        print("clear the volumes from the scene")

        vlist = volume_list(self.session)
        for v in vlist:
            v.delete()
            
        print("opening the volume...")
        #print(self.settings)
        print(self.settings.view_target_vol_path)
        self.vol = run(self.session, "open {0}".format(self.settings.view_target_vol_path))[0]

        N_mol, N_quat, N_shift, N_iter, N_metric = e_sqd_log.shape
        self.e_sqd_log = e_sqd_log.reshape([N_mol, N_quat * N_shift, N_iter, N_metric])
        self.e_sqd_clusters_ordered = cluster_and_sort_sqd_fast(self.e_sqd_log, self.settings.clustering_shift_tolerance, self.settings.clustering_angle_tolerance)
        
        self.model = TableModel(self.e_sqd_clusters_ordered, self.e_sqd_log)
        self.proxyModel = QSortFilterProxyModel()
        self.proxyModel.setSourceModel(self.model)
        
        self.view.setModel(self.proxyModel)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.reset()
        self.view.show()  
        
        self.stats.setText("stats: {0} entries".format(self.model.rowCount())) 
        
        print("showing the first cluster")
        self.mol_folder = self.settings.view_structures_directory
        self.cluster_idx = 0
        # look_at_cluster(self.e_sqd_clusters_ordered, self.mol_folder, self.cluster_idx, self.session)
        
    def run_button_clicked(self):
        #import sys
        #sys.path.append('D:\\GIT\\DiffFitViewer\\src')
        print("Running the computation...")

        #target_vol_path = "D:\\GIT\\DiffFitViewer\dev_data\input\domain_fit_demo_3domains\density2.mrc"
        #output_folder = "D:\\GIT\\DiffFitViewer\dev_data\output"                
        
        e_sqd_log = diff_atom_comp(
            target_vol_path=self.settings.target_vol_path,
            target_surface_threshold=self.settings.target_surface_threshold,
            min_cluster_size=self.settings.min_cluster_size,
            structures_dir=self.settings.structures_directory,
            structures_sim_map_dir=self.settings.structures_sim_map_dir,
            N_shifts=self.settings.N_shifts,
            N_quaternions=self.settings.N_quaternions,
            negative_space_value=self.settings.negative_space_value,
            exp_name=self.settings.exp_name,
            learning_rate=self.settings.learning_rate,
            n_iters=self.settings.N_iters,
            out_dir=self.settings.output_directory,
            out_dir_exist_ok=self.settings.out_dir_exist_ok,
            conv_loops=self.settings.conv_loops,
            conv_kernel_sizes=self.settings.conv_kernel_sizes,
            conv_weights=self.settings.conv_weights
        )

        # copy the directories
        self.target_vol.setText(self.settings.target_vol_path)     
        self.structures_folder.setText(self.settings.structures_directory)
        self.dataset_folder.setText("{0}\{1}".format(self.settings.output_directory, self.settings.exp_name))            
        #print(self.settings)
        
        # output is tensor
        self.show_results(e_sqd_log.detach().cpu().numpy())
        
    def init_button_clicked(self):            
        if self.settings is None:
            return
            
        datasetoutput = self.settings.view_output_directory        
        
        if len(datasetoutput) == 0:
            print("Specify the datasetoutput folder first!")
            return
                
        print("loading data...")
        e_sqd_log = np.load("{0}\\e_sqd_log.npy".format(datasetoutput))
        
        #print(e_sqd_log)
        self.show_results(e_sqd_log)
        
    def save_button_clicked(self):          
        if not self.mol:
            return
        
        fileName, ext = self.select_clicked("Save File", self.view, True, "CIF Files(*.cif);;PDB Files (*.pdb)")           
        
        self.save_structure(fileName, ext)
    
    def save_structure(self, targetpath, ext):
        
        if len(targetpath) > 0 and self.mol:
            run(self.session, "save '{0}.{1}' models #{2}".format(targetpath, ext, self.mol.id[0]))
    
    def simulate_volume_clicked(self): 
        resolution = self.simulate_volume_resolution.value()
        self.mol_vol = simulate_volume(self.session, self.vol, self.mol_folder, self.mol_idx, self.transformation, resolution)
        return
        
    def zero_density_button_clicked(self):      
        if self.vol is None:
            print("You have to select a row first!")
            return
            
        if self.mol_vol is None:
            print("You have to simulate a volume first!")
            return

        work_vol = zero_cluster_density(self.session, self.mol_vol, self.mol, self.vol, self.cluster_idx)
        self.vol = work_vol
        return
    
    def progress_value_changed(self):
        progress = self.progress.value()
        self.progress_label.setText("{0}/{1}".format(progress, self.progress.maximum()))
        
        if self.e_sqd_log is not None and self.mol is not None:
            self.transformation = get_transformation_at_record(self.e_sqd_log, self.mol_idx, self.record_idx, progress - 1)
            self.mol.scene_position = self.transformation
    