import pandas as pd
import numpy as np
import re
import os

# def calculate_distance_to_vector(point, vector_point, vector_direction):
#     vector_point = np.array(vector_point)
#     vector_direction = np.array(vector_direction)
#     point = np.array(point)

#     unit_vector = vector_direction / np.linalg.norm(vector_direction)
#     vector_to_point = point - vector_point
#     distance_along_vector = np.dot(vector_to_point, unit_vector)

#     return distance_along_vector

def determineFCSVCoordSystem(input_fcsv,overwrite_fcsv=False):
    # need to determine if file is in RAS or LPS
    # loop through header to find coordinate system
    coordFlag = re.compile('# CoordinateSystem')
    verFlag = re.compile('# Markups fiducial file version')
    headFlag = re.compile('# columns')
    coord_sys=None
    headFin=None
    ver_fin=None

    with open(input_fcsv, 'r') as myfile:
        firstNlines=myfile.readlines()[0:3]

    for row in firstNlines:
        row=re.sub("[\s\,]+[\,]","",row).replace("\n","")
        cleaned_dict={row.split('=')[0].strip():row.split('=')[1].strip()}
        if None in list(cleaned_dict):
            cleaned_dict['# columns'] = cleaned_dict.pop(None)
        if any(coordFlag.match(x) for x in list(cleaned_dict)):
            coord_sys = list(cleaned_dict.values())[0]
        if any(verFlag.match(x) for x in list(cleaned_dict)):
            verString = list(filter(verFlag.match,  list(cleaned_dict)))
            assert len(verString)==1
            ver_fin = verString[0].split('=')[-1].strip()
        if any(headFlag.match(x) for x in list(cleaned_dict)):
            headFin=list(cleaned_dict.values())[0].split(',')


    if any(x in coord_sys for x in {'LPS','1'}):
        df = pd.read_csv(input_fcsv, skiprows=3, header=None)

        if df.shape[1] != 13:
            df=df.iloc[:,:14]

        df[1] = -1 * df[1] # flip orientation in x
        df[2] = -1 * df[2] # flip orientation in y

        if overwrite_fcsv:
            with open(input_fcsv, 'w') as fid:
                fid.write("# Markups fiducial file version = 4.11\n")
                fid.write("# CoordinateSystem = 0\n")
                fid.write("# columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID\n")

            df.rename(columns={0:'node_id', 1:'x', 2:'y', 3:'z', 4:'ow', 5:'ox',
                                6:'oy', 7:'oz', 8:'vis', 9:'sel', 10:'lock',
                                11:'label', 12:'description', 13:'associatedNodeID'}, inplace=True)

            df['associatedNodeID']= pd.Series(np.repeat('',df.shape[0]))
            df.round(6).to_csv(input_fcsv, sep=',', index=False, lineterminator="", mode='a', header=False, float_format='%.6f')

            print(f"Converted LPS to RAS: {os.path.dirname(input_fcsv)}/{os.path.basename(input_fcsv)}")
    return coord_sys,headFin


def create_electrode_list(df_te):
    electrodes = []
    for i in range(0, len(df_te), 2):
        target_point = df_te.iloc[i][[1, 2, 3]].values
        entry_point = df_te.iloc[i + 1][[1, 2, 3]].values
        electrode_label = df_te.iloc[i][11]

        electrodes.append({
            'entry_point': entry_point,
            'target_point': target_point,
            'contacts': [],
            'elec_label': electrode_label
        })
    return electrodes

def calculate_distance_to_line(point, line_point, line_direction):
    line_point = np.array(line_point)
    line_direction = np.array(line_direction)
    point = np.array(point)

    unit_vector = line_direction / np.linalg.norm(line_direction)
    vector_to_point = point - line_point
    projection_length = np.dot(vector_to_point, unit_vector)
    projection_point = line_point + projection_length * unit_vector

    if projection_length <= np.linalg.norm(line_direction):
      distance = np.linalg.norm(point - projection_point)
      return distance
    else:
      return None

def assign_contacts_to_electrodes(electrodes, contacts, max_distance_threshold=4.0):

    for contact in contacts:
        min_distance = float('inf')
        assigned_electrode = None

        for electrode in electrodes:
            entry_point = electrode['entry_point']
            target_point = electrode['target_point']
            direction_vector = target_point - entry_point

            distance = calculate_distance_to_line(contact, entry_point, direction_vector)
            if distance and distance <= max_distance_threshold and distance < min_distance:
                min_distance = distance
                assigned_electrode = electrode

        if assigned_electrode:
            assigned_electrode['contacts'].append(contact)

    return electrodes

def new_label_contacts(target_point, contacts, electrode_label):
  contacts = np.array(contacts, dtype = np.float64)
  target_point = np.array(target_point)
  # distances = np.linalg.norm(contacts - target_point, axis=1)
  distances = [np.sqrt(np.sum((point - target_point)**2)) for point in contacts]
  sorted_indices = np.argsort(distances)

#   contact_labels = [f"{electrode_label}{i+1}" for i in range(len(contacts))]
  contact_labels = [f"{electrode_label}-{i+1:02}" for i in range(len(contacts))]

  print(sorted_indices)
  sorted_contact_labels = [contact_labels[i] for i in sorted_indices]

  renamed_labels = [sorted_contact_labels[i] for i in range(len(sorted_indices))]
  print(renamed_labels)

  # Update dictionary with new labels
  return np.array(renamed_labels)

def label_multiple_electrodes(electrodes):
    for electrode in electrodes:
      if electrode['contacts']:
        electrode['contact_labels'] = new_label_contacts(electrode['target_point'],  electrode['contacts'], electrode['elec_label'])
    return electrodes

def convert_to_df(labelled_final):
  new_contacts_dicts = []

  # Iterate through each electrode in the labeled electrodes list
  for electrode in labelled_final:
      elec_label = electrode.get('elec_label', '')
      contact_labels = electrode.get('contact_labels', [])
      contacts = electrode.get('contacts', [])

      # Iterate through each contact and corresponding label
      for label, contact in zip(contact_labels, contacts):
          contact_dict = {
              'x': contact[0],
              'y': contact[1],
              'z': contact[2],
              'contact_label': f"{label}",  # Combine electrode label with contact label
          }
          new_contacts_dicts.append(contact_dict)

  # Display the new list of contact dictionaries
  new_df = pd.DataFrame(new_contacts_dicts)
  return new_df
def df_to_fcsv(input_df, output_fcsv):
    with open(output_fcsv, 'w') as fid:
        fid.write("# Markups fiducial file version = 4.11\n")
        fid.write("# CoordinateSystem = 0\n")
        fid.write("# columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID\n")

    out_df={'node_id':[],'x':[],'y':[],'z':[],'ow':[],'ox':[],'oy':[],'oz':[],
        'vis':[],'sel':[],'lock':[],'label':[],'description':[],'associatedNodeID':[]
    }

    for idx,ifid in input_df.iterrows():
        out_df['node_id'].append(idx+1)
        out_df['x'].append(ifid.iloc[0])
        out_df['y'].append(ifid.iloc[1])
        out_df['z'].append(ifid.iloc[2])
        out_df['ow'].append(0)
        out_df['ox'].append(0)
        out_df['oy'].append(0)
        out_df['oz'].append(0)
        out_df['vis'].append(1)
        out_df['sel'].append(1)
        out_df['lock'].append(1)
        out_df['label'].append(str(ifid.iloc[3]))
        out_df['description'].append('NA')
        out_df['associatedNodeID'].append('')

    out_df=pd.DataFrame(out_df)
    out_df.to_csv(output_fcsv, sep=',', index=False, lineterminator="", mode='a', header=False, float_format = '%.3f')

if __name__ == "__main__":
    determineFCSVCoordSystem(snakemake.input['planned_fcsv'], overwrite_fcsv=True)
    determineFCSVCoordSystem(snakemake.input['coords'], overwrite_fcsv=True)

    df_te = pd.read_csv(snakemake.input['planned_fcsv'], skiprows = 3, header = None)
    df_contacts = pd.read_csv(snakemake.input['coords'], skiprows = 3, header = None)

    contact_array = df_contacts[[1, 2, 3]].values

    electrode_list = create_electrode_list(df_te)
    grouped = assign_contacts_to_electrodes(electrode_list, contact_array, 5.0)
    
  # Label contacts for each electrode
    labelled_contacts = label_multiple_electrodes(electrode_list)
    labelled_df = convert_to_df(labelled_contacts)

    df_to_fcsv(labelled_df, snakemake.output['labelled_coords'])        

