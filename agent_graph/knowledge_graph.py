
import json
import os
import networkx as nx
from typing import List, Dict, Any, Optional

class KnowledgeGraph:
    def __init__(self, data_path: str = None):
        if data_path is None:
            # We are in D:\herbguard\herbaguard\agent_graph\knowledge_graph.py
            # The database folder is in D:\herbguard\herbaguard\database
            # So we go up one level to D:\herbguard\herbaguard
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.abspath(os.path.join(current_dir, ".."))
        
        self.data_path = data_path
        self.graph = nx.Graph()
        self._load_data()

    def _load_data(self):
        # Database files are in D:\herbguard\herbaguard\database
        herb_file = os.path.join(self.data_path, "database", "data.json")
        drug_file = os.path.join(self.data_path, "database", "data_drug.json")
        interaction_file = os.path.join(self.data_path, "database", "interaction.json")

        # 1. Load Herbs
        print(f"Loading Herbs from {herb_file}...")
        try:
            with open(herb_file, "r", encoding="utf-8") as f:
                herbs = json.load(f)
                for h in herbs:
                    # Use unique ID prefix to avoid collision
                    node_id = f"herb_{h['herb_id']}"
                    # Name is not explicitly in file, use first alias as name
                    name = h.get('name')
                    if not name and h.get('aliases'):
                        name = h['aliases'][0]
                    elif not name:
                        name = f"Herb ID {h['herb_id']}"

                    self.graph.add_node(
                        node_id, 
                        type="herb", 
                        official_id=h['herb_id'], 
                        name=name, 
                        aliases=[a.lower() for a in h.get("aliases", [])]
                    )
        except Exception as e:
            print(f"Error loading herbs: {e}")

        # 2. Load Drugs
        print(f"Loading Drugs from {drug_file}...")
        try:
            with open(drug_file, "r", encoding="utf-8") as f:
                drugs = json.load(f)
                for d in drugs:
                    node_id = f"drug_{d['drug_id']}"
                    # Name is not explicitly in file, use first alias as name
                    name = d.get('name')
                    if not name and d.get('aliases'):
                        name = d['aliases'][0]
                    elif not name:
                         name = f"Drug ID {d['drug_id']}"

                    self.graph.add_node(
                        node_id, 
                        type="drug", 
                        official_id=d['drug_id'], 
                        name=name,
                        aliases=[a.lower() for a in d.get("aliases", [])]
                    )
        except Exception as e:
            print(f"Error loading drugs: {e}")

        # 3. Load Interactions
        print(f"Loading Interactions from {interaction_file}...")
        try:
            with open(interaction_file, "r", encoding="utf-8") as f:
                interactions = json.load(f)
                if isinstance(interactions, dict): 
                    interactions = [interactions] # handle single obj case
                
                for i in interactions:
                    herb_node = f"herb_{i['herb_id']}"
                    drug_node = f"drug_{i['drug_id']}"
                    
                    if self.graph.has_node(herb_node) and self.graph.has_node(drug_node):
                        self.graph.add_edge(
                            herb_node, 
                            drug_node, 
                            relation="INTERACTS_WITH", 
                            details=i['interaction']
                        )
                    else:
                        print(f"Skipping interaction: Missing node {herb_node} or {drug_node}")
        except Exception as e:
            print(f"Error loading interactions: {e}")
            
        print(f"Graph Built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")

    def find_node_by_name(self, name: str, node_type: str = None) -> List[Dict[str, Any]]:
        """
        Search for nodes where the name or alias matches the query string.
        Returns a list of matching node dictionaries.
        """
        query = name.lower().strip()
        matches = []
        
        for node_id, data in self.graph.nodes(data=True):
            # Filtering
            if node_type and data.get("type") != node_type:
                continue
            
            # Simple substring or exact match check
            # For robustness, we check if query is in aliases
            if query in data.get("aliases", []):
                matches.append({
                    "id": data["official_id"], # integer ID for internal logic
                    "node_id": node_id,        # graph string ID
                    "name": data["name"],
                    "type": data["type"]
                })
                
        return matches

    def check_interaction(self, herb_id: int, drug_id: int) -> Dict[str, Any]:
        """
        Check if an edge exists between herb_ID and drug_ID.
        """
        h_node = f"herb_{herb_id}"
        d_node = f"drug_{drug_id}"
        
        if self.graph.has_edge(h_node, d_node):
            edge_data = self.graph.get_edge_data(h_node, d_node)
            return {
                "status": "interaction_found",
                "herb_id": herb_id,
                "drug_id": drug_id,
                "data": edge_data["details"]
            }
        
        return {
            "status": "no_interaction_found",
            "herb_id": herb_id,
            "drug_id": drug_id
        }

if __name__ == "__main__":
    kg = KnowledgeGraph()
    print("Testing Search 'Panadol'...", kg.find_node_by_name("Panadol"))
    print("Testing Search 'Nhân sâm'...", kg.find_node_by_name("Nhân sâm"))
