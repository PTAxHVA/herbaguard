
import os
import networkx as nx
from pyvis.network import Network
from knowledge_graph import KnowledgeGraph

if __name__ == "__main__":
    print("Building Knowledge Graph...")
    # Initialize your graph logic (loads data from JSONs)
    kg = KnowledgeGraph()
    G = kg.graph

    print(f"Graph stats: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Create PyVis Network
    # USE CDN=TRUE to ensure javascript libraries are loaded even if local files are missing
    net = Network(height="750px", width="100%", bgcolor="#222222", font_color="white", select_menu=True, filter_menu=True, cdn_resources='remote')
    
    # Iterate over nodes and add them with colors based on type
    for node_id, data in G.nodes(data=True):
        node_type = data.get("type", "unknown")
        label = data.get("name", node_id)
        if hasattr(label, 'encode'): label = label # ensure string
        
        color = "#97C2FC" # default blue
        if node_type == "herb":
            color = "#00ff00" # green for herbs
        elif node_type == "drug":
            color = "#ff0000" # red for drugs
            
        # Add node to PyVis
        net.add_node(node_id, label=label, title=f"Type: {node_type}\nID: {data.get('official_id')}", color=color)

    # Iterate over edges and add them
    for source, target, data in G.edges(data=True):
        # Interaction details as hover text
        interaction_text = str(data.get("details", "Interacts"))
        try: 
            # If details is a dict/json, make it pretty
            import json
            if isinstance(data.get("details"), dict):
                interaction_text = json.dumps(data.get("details"), indent=2, ensure_ascii=False)
            elif isinstance(data.get("details"), str):
                interaction_text = data.get("details")
        except:
            pass

        net.add_edge(source, target, title=interaction_text, color="#FFFF00") # Yellow edges

    # Physics options for better layout
    net.barnes_hut()
    
    # Save the visualization
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "herb_drug_network.html")
    print(f"Saving visualization to: {output_file}")
    net.save_graph(output_file)
    
    print("Done! Open 'herb_drug_network.html' in your browser to explore the graph.")
