import re

class ProlifDarkThemeEditor:
    """
    OOP class untuk mengubah HTML ProLIF ke tema gelap
    Input dan output berupa string HTML
    """
    
    def __init__(self, custom_colors=None):
        """
        Initialize ProlifDarkThemeEditor
        
        Args:
            custom_colors (dict): Custom color mapping untuk node groups
        """
        self.dark_css = """
            body {
                padding: 0;
                margin: 0;
                background: #1a1a1a;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            .legend-btn.residues.disabled {
                background: #404040 !important;
                color: #888 !important;
            }
            .legend-btn.interactions.disabled {
                border-color: #404040 !important;
                color: #888 !important;
                background: #2a2a2a !important;
            }
            #mynetwork {
                background: #2a2a2a;
                border: 1px solid #404040;
            }
            #networklegend {
                background: #2a2a2a;
                padding: 15px;
                border-radius: 8px;
                border: 1px solid #404040;
                margin-top: 10px;
            }
            .legend-btn {
                margin: 4px;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 13px;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .legend-btn:hover {
                opacity: 0.8;
                transform: translateY(-1px);
            }
            .legend-btn.residues {
                border: none;
                color: #1a1a1a;
                font-weight: 500;
            }
            .legend-btn.interactions {
                background: #2a2a2a;
                color: #e0e0e0;
                border-width: 2px;
                border-style: dashed;
            }
        """
        
        # Default color mapping untuk node groups
        self.default_colors = {
            "protein": "#4a90e2",  # Blue untuk protein
            "ligand": "#7ed321",   # Green untuk ligand
            "interaction": "#f5a623"  # Orange untuk interaction
        }
        
        # Set custom colors atau gunakan default
        self.color_mapping = custom_colors if custom_colors else self.default_colors
    
    def _replace_css_styles(self, html_content):
        """
        Mengganti CSS styles dengan dark theme
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: HTML dengan CSS dark theme
        """
        css_pattern = r'<style type="text/css">(.*?)</style>'
        html_content = re.sub(css_pattern, f'<style type="text/css">{self.dark_css}</style>', 
                            html_content, flags=re.DOTALL)
        return html_content
    
    def _replace_node_colors(self, html_content):
        """
        Mengganti warna node yang hitam dengan warna dark theme
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: HTML dengan node colors yang diupdate
        """
        # Ganti node dengan color black menjadi light gray
        node_pattern = r'("color":\s*"black")'
        html_content = re.sub(node_pattern, r'"color": "#e0e0e0"', html_content)
        return html_content
    
    def _replace_edge_colors(self, html_content):
        """
        Mengganti warna edge yang hitam dengan warna dark theme
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: HTML dengan edge colors yang diupdate
        """
        # Update edge colors - metode pertama
        edge_pattern = r'("from":\s*\d+,\s*"to":\s*\d+,\s*"color":\s*"black")'
        html_content = re.sub(edge_pattern, 
                            lambda m: m.group(0).replace('"color": "black"', '"color": "#b0b0b0"'), 
                            html_content)
        
        # Alternatif untuk edge yang lebih spesifik
        edge_pattern2 = r'({"from":\s*\d+,.*?"color":\s*"black".*?})'
        def replace_edge_color(match):
            return match.group(0).replace('"color": "black"', '"color": "#b0b0b0"')
        
        html_content = re.sub(edge_pattern2, replace_edge_color, html_content)
        return html_content
    
    def _update_network_options(self, html_content):
        """
        Update network configuration options

        Args:
            html_content (str): HTML content

        Returns:
            str: HTML dengan network options yang diupdate
        """
        # Fix invalid vis.js options: configure -> solver, and add proper interaction settings
        html_content = re.sub(r'"configure":\s*{[^}]*}', '"solver": {"forceAtlas2Based": {"gravitationalConstant": -50, "centralGravity": 0.01, "springLength": 100, "springConstant": 0.08, "damping": 0.4, "avoidOverlap": 0}}', html_content)

        # Add proper interaction options at the top level
        options_pattern = r'("options"\s*:\s*{)'
        def add_interaction_options(match):
            return match.group(0) + '"interaction": {"hover": true, "multiselect": true}, '

        html_content = re.sub(options_pattern, add_interaction_options, html_content)
        return html_content
    
    def _update_legend_colors(self, html_content):
        """
        Update legend color variables
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: HTML dengan legend colors yang diupdate
        """
        legend_pattern = r'var color = "white";'
        html_content = re.sub(legend_pattern, 'var color = "dark";', html_content)
        return html_content
    
    def _customize_node_group_colors(self, html_content):
        """
        Mengustomisasi warna node berdasarkan group mapping
        
        Args:
            html_content (str): HTML content
            
        Returns:
            str: HTML dengan custom node colors
        """
        for group, color in self.color_mapping.items():
            # Update warna berdasarkan group
            pattern = rf'("group":\s*"{group}"[^}}]*"color":\s*)"[^"]*"'
            replacement = rf'\1"{color}"'
            html_content = re.sub(pattern, replacement, html_content)
        
        return html_content
    
    def apply_dark_theme(self, html_content):
        """
        Mengaplikasikan dark theme ke HTML ProLIF
        
        Args:
            html_content (str): String HTML ProLIF original
            
        Returns:
            str: String HTML dengan dark theme
        """
        # Validasi input
        if not isinstance(html_content, str):
            raise ValueError("Input harus berupa string HTML")
        
        if not html_content.strip():
            raise ValueError("HTML content tidak boleh kosong")
        
        # Apply transformations step by step
        html_content = self._replace_css_styles(html_content)
        html_content = self._replace_node_colors(html_content)
        html_content = self._replace_edge_colors(html_content)
        html_content = self._update_network_options(html_content)
        html_content = self._update_legend_colors(html_content)
        html_content = self._customize_node_group_colors(html_content)
        
        return html_content
    
    def set_custom_colors(self, color_mapping):
        """
        Set custom color mapping untuk node groups
        
        Args:
            color_mapping (dict): Dictionary dengan mapping group -> color
        """
        if not isinstance(color_mapping, dict):
            raise ValueError("Color mapping harus berupa dictionary")
        
        self.color_mapping = color_mapping
    
    def get_current_colors(self):
        """
        Get current color mapping
        
        Returns:
            dict: Current color mapping
        """
        return self.color_mapping.copy()
    
    def reset_colors(self):
        """
        Reset color mapping ke default
        """
        self.color_mapping = self.default_colors.copy()